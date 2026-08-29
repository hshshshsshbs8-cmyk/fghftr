"""Load, save and encrypt the protected identity configuration.

The config lives at ``config/protected.yaml``. After the first load it is
encrypted at rest with Fernet; the key is kept in ``config/.scrubpup.key``
(mode 600) or supplied via the ``SCRUBPUP_KEY`` environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from cryptography.fernet import Fernet, InvalidToken

from .utils import config_dir, get_logger

ENC_MARKER = b"SCRUBPUP-ENC:v1:"
CONFIG_NAME = "protected.yaml"
KEY_NAME = ".scrubpup.key"

log = get_logger("scrubpup.config")


class ConfigError(RuntimeError):
    pass


@dataclass
class Identity:
    name: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    usernames: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    social_handles: list[str] = field(default_factory=list)

    def identifiers(self, target: str | None = None) -> list[tuple[str, str]]:
        """Return ``(type, value)`` pairs, optionally filtered by type."""
        groups = {
            "email": self.emails,
            "phone": self.phones,
            "username": self.usernames + self.social_handles,
            "address": self.addresses,
        }
        if self.name:
            groups["name"] = [self.name]
        pairs: list[tuple[str, str]] = []
        for kind, values in groups.items():
            if target and kind != target:
                continue
            pairs.extend((kind, v) for v in dict.fromkeys(values) if v)
        return pairs


@dataclass
class Settings:
    scan_interval_hours: int = 24
    rate_limit_per_sec: float = 2.0
    notifier: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)


@dataclass
class Config:
    identity: Identity = field(default_factory=Identity)
    settings: Settings = field(default_factory=Settings)

    def to_dict(self) -> dict:
        return {
            "identity": {
                "name": self.identity.name,
                "emails": self.identity.emails,
                "phones": self.identity.phones,
                "usernames": self.identity.usernames,
                "addresses": self.identity.addresses,
                "social_handles": self.identity.social_handles,
            },
            "settings": {
                "scan_interval_hours": self.settings.scan_interval_hours,
                "rate_limit_per_sec": self.settings.rate_limit_per_sec,
                "notifier": self.settings.notifier,
                "sources": self.settings.sources,
            },
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Config:
        ident = raw.get("identity") or {}
        sett = raw.get("settings") or {}
        return cls(
            identity=Identity(
                name=str(ident.get("name") or ""),
                emails=[str(v) for v in ident.get("emails") or []],
                phones=[str(v) for v in ident.get("phones") or []],
                usernames=[str(v) for v in ident.get("usernames") or []],
                addresses=[str(v) for v in ident.get("addresses") or []],
                social_handles=[str(v) for v in ident.get("social_handles") or []],
            ),
            settings=Settings(
                scan_interval_hours=int(sett.get("scan_interval_hours") or 24),
                rate_limit_per_sec=float(sett.get("rate_limit_per_sec") or 2.0),
                notifier=dict(sett.get("notifier") or {}),
                sources=dict(sett.get("sources") or {}),
            ),
        )


def config_path() -> Path:
    return config_dir() / CONFIG_NAME


def key_path() -> Path:
    return config_dir() / KEY_NAME


def load_key(*, create: bool = False) -> bytes:
    env = os.environ.get("SCRUBPUP_KEY")
    if env:
        return env.encode()
    path = key_path()
    if path.exists():
        return path.read_bytes().strip()
    if not create:
        raise ConfigError(f"no encryption key: set SCRUBPUP_KEY or create {path}")
    key = Fernet.generate_key()
    path.write_bytes(key)
    path.chmod(0o600)
    log.info("generated new encryption key at %s", path)
    return key


def is_encrypted(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(len(ENC_MARKER)) == ENC_MARKER
    except OSError:
        return False


def encrypt_file(path: Path, key: bytes) -> None:
    if is_encrypted(path):
        return
    token = Fernet(key).encrypt(path.read_bytes())
    path.write_bytes(ENC_MARKER + token)
    path.chmod(0o600)


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    if not blob.startswith(ENC_MARKER):
        return blob
    try:
        return Fernet(key).decrypt(blob[len(ENC_MARKER):])
    except InvalidToken as exc:
        raise ConfigError("wrong key: cannot decrypt protected.yaml") from exc


def load_config(path: Path | None = None, *, encrypt_after: bool = True) -> Config:
    """Load the config, encrypting the plaintext file at rest afterwards."""
    path = path or config_path()
    if not path.exists():
        raise ConfigError(f"{path} not found - run `scrubpup init` first")
    key = load_key(create=True)
    raw_bytes = decrypt_bytes(path.read_bytes(), key)
    raw = yaml.safe_load(raw_bytes) or {}
    if encrypt_after and not is_encrypted(path):
        encrypt_file(path, key)
        log.info("encrypted %s at rest", path)
    return Config.from_dict(raw)


def save_config(config: Config, path: Path | None = None, *, encrypt: bool = True) -> Path:
    path = path or config_path()
    plaintext = yaml.safe_dump(config.to_dict(), sort_keys=False).encode()
    if encrypt:
        key = load_key(create=True)
        path.write_bytes(ENC_MARKER + Fernet(key).encrypt(plaintext))
        path.chmod(0o600)
    else:
        path.write_bytes(plaintext)
    return path


def decrypt_to_plaintext(path: Path | None = None) -> Path:
    """Temporarily restore plaintext YAML (used by ``config edit``)."""
    path = path or config_path()
    key = load_key()
    path.write_bytes(decrypt_bytes(path.read_bytes(), key))
    return path
