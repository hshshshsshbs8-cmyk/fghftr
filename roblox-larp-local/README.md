# ◈ LarpLab

A polished, original Chromium extension for **local Roblox UI simulation and roleplay**.

## Features

- Simulated Robux balance
- Local username/display-name simulation
- Premium and verification toggles
- Local simulated inventory
- Persistent state with `chrome.storage.local`
- MutationObserver-driven UI overlay that survives SPA rerenders
- Reset/apply controls
- No credentials, cookies, purchases, or server-side account changes

## Install locally

1. Open `chrome://extensions`, `opera://extensions`, or the equivalent Chromium extensions page.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select the `roblox-larp-local` directory.
5. Open Roblox and configure the simulator from the extension popup.

## Scope

LarpLab is intentionally a **local simulator**. Its simulated Robux, inventory, and profile values are not sent to Roblox and do not represent real account ownership. It does not implement transaction forgery, authorization bypass, credential collection, or server-side inventory modification.

Inspired by the general concept of Roblox UI larping tools, but implemented as an original project rather than a copy of another repository.
