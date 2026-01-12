"""Configuration for Sonos dial controller."""

import os
from dotenv import load_dotenv

load_dotenv()

# Volume adjustment per dial tick (percentage points)
VOLUME_STEP = 1

# How often to re-scan for active speaker (seconds)
ACTIVE_SPEAKER_POLL_INTERVAL = 5.0

# Device name pattern to look for (the Peakzooc dial)
DIAL_DEVICE_NAME_PATTERN = "Keyboard"

# Hue configuration
HUE_BRIDGE_IP = os.getenv("HUE_BRIDGE_IP")  # Fallback IP if discovery fails
HUE_CONFIG_FILE = os.path.expanduser("~/.sonos-dial-hue")
HUE_ZONES = os.getenv("HUE_ZONES", "").split(",") if os.getenv("HUE_ZONES") else []
HUE_BRIGHTNESS_STEP = 25  # Brightness adjustment per dial tick (0-254 scale, ~10% per tick)
