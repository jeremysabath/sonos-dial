# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Raspberry Pi Zero 2W + Peakzooc wireless dial → Sonos/Hue controller. The dial sends USB HID events (`KEY_VOLUMEUP`, `KEY_VOLUMEDOWN`, `KEY_MUTE`) which are translated to Sonos or Hue API calls depending on mode.

**Quadruple-click** toggles between Sonos mode (volume/playback) and Hue mode (brightness/on-off).

## Setup

Copy `.env.example` to `.env` and configure your values:
```bash
cp .env.example .env
# Edit .env with your PI_HOST, PI_USER, PI_PATH, HUE_BRIDGE_IP, HUE_ZONES
```

## Commands

```bash
# Deploy to Pi and restart service
./deploy.sh && ssh $PI_USER@$PI_HOST "sudo systemctl restart sonos-dial"

# View logs on Pi
ssh $PI_USER@$PI_HOST "sudo journalctl -u sonos-dial -n 50 --no-pager"

# Local testing without hardware (mock mode reads +/-/p from stdin, 4 for quadruple-click)
python src/main.py --mock
```

## Architecture

```
dial_input.py    # evdev async event loop, multi-click detection (debounce-based)
     ↓ callbacks
main.py          # SonosDialController: mode switching, routes dial→sonos or dial→hue
     ↓
sonos_control.py # SoCo wrapper: discover, volume, play/pause, next/prev
hue_control.py   # phue wrapper: discover bridge, brightness, toggle, flash
```

**Key design decisions:**
- All network calls (Sonos/Hue) run in thread pool via `run_in_executor()` to avoid blocking asyncio
- Multi-click detection uses debounce timing (0.30s window), resolves immediately at MAX_CLICKS (4)
- Quadruple-click for mode switch (long press doesn't work - dial sends instant key-up regardless of hold duration)
- Hue brightness uses throttling (150ms, ~7 updates/sec) with trailing update to prevent out-of-order API responses
- State persisted to `~/.sonos-dial-*` files: last speaker, mode, hue zone, hue credentials

## Configuration

Edit `src/config.py`:
- Sonos: `VOLUME_STEP`, `ACTIVE_SPEAKER_POLL_INTERVAL`, `DIAL_DEVICE_NAME_PATTERN`
- Hue: `HUE_ZONES` (zones to cycle), `HUE_BRIGHTNESS_STEP`, `HUE_BRIDGE_IP` (or auto-discover)
