"""Configuration for Sonos dial controller."""

import os

# Volume adjustment per dial tick (percentage points)
VOLUME_STEP = 3

# How often to re-scan for active speaker (seconds)
ACTIVE_SPEAKER_POLL_INTERVAL = 5.0

# Device name pattern to look for (the Peakzooc dial)
DIAL_DEVICE_NAME_PATTERN = "Keyboard"

# Hue configuration
HUE_BRIDGE_IP = None  # Auto-discover if None, or set explicit IP
HUE_CONFIG_FILE = os.path.expanduser("~/.sonos-dial-hue")
HUE_ZONES = ["All Kitchen", "Stove Room", "Office"]  # Zones to cycle through
HUE_BRIGHTNESS_STEP = 25  # Brightness adjustment per dial tick (0-254 scale, ~10% per tick)
