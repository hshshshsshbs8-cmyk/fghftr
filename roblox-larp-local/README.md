# LarpLab

A clean, original Chromium extension for **local-only Roblox UI simulation and roleplay**.

## Features

- Simulated Robux balance
- Simulated username/display name
- Local Premium toggle/state
- Local simulated inventory/equipped state foundation
- Persistent state via `chrome.storage.local`
- MutationObserver-based UI re-application for SPA rerenders
- Clearly labeled local-only simulator panel

## Safety boundary

LarpLab intentionally does **not** make Roblox purchases, grant Robux, forge transactions, modify server-side ownership, bypass authorization, or collect session cookies/passwords. The simulated state exists only in the extension's local storage and browser UI.

## Install locally

1. Download/clone this repository.
2. Open `chrome://extensions` (or the equivalent extensions page in your Chromium browser).
3. Enable Developer mode.
4. Choose **Load unpacked** and select `roblox-larp-local/`.
5. Open Roblox and use the extension popup to configure the simulated profile.

This project is an independent implementation inspired by the general concept of Roblox UI larping; it is not a copy of any third-party repository.
