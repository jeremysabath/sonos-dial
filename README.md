# Sonos Dial Controller

A Raspberry Pi Zero 2W project that turns a Peakzooc wireless dial into a controller for Sonos speakers and Philips Hue lights.

## Controls

**Quadruple-click** to switch between Sonos and Hue modes.

### Sonos Mode
| Action | Function |
|--------|----------|
| Rotate | Adjust volume |
| Single click | Play/pause |
| Double click | Next track |
| Triple click | Previous track |

### Hue Mode
| Action | Function |
|--------|----------|
| Rotate | Adjust brightness |
| Single click | Toggle on/off |
| Double click | Cycle to next zone (with flash) |

## Hardware

- Raspberry Pi Zero 2W
- Peakzooc desktop volume knob (2.4G wireless version)
- Micro-USB OTG adapter (Pi Zero's data port is micro-USB, dial receiver is USB-A)
- USB-C power supply for the Pi
- MicroSD card (8GB+)

## Architecture

```
[Dial] --2.4G USB--> [Pi Zero 2W] --WiFi--> [Sonos Speakers]
                          |                  [Hue Bridge]
                     Python service
                   (evdev + soco + phue)
```

The dial presents as a USB HID keyboard, sending `KEY_VOLUMEUP`, `KEY_VOLUMEDOWN`, and `KEY_MUTE` events. The Python service reads these via `evdev` and translates them to Sonos API calls via `soco` or Hue API calls via `phue`.

## Pi Setup

### 1. Flash SD Card

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Select: **Raspberry Pi Zero 2W** → **Raspberry Pi OS Lite (64-bit)**
3. Click gear/settings icon and configure:
   - Hostname (e.g., `pi-zero`)
   - Enable SSH with password
   - Set username/password
   - WiFi: your **2.4GHz** network (Pi Zero 2W doesn't support 5GHz)
   - Timezone
4. Write to SD card

### 2. First Boot

```bash
# Insert SD card, plug in power, wait 2-3 minutes
ping <hostname>.local

# SSH in
ssh <username>@<hostname>.local
```

### 3. Initial Configuration

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv

# Add user to input group (for evdev access to /dev/input)
sudo usermod -a -G input $USER

# Reboot to apply group change
sudo reboot
```

### 4. Deploy Code

From your development machine:

```bash
# Set up SSH key auth for passwordless access
ssh-copy-id <username>@<hostname>.local

# Deploy
./deploy.sh
```

On the Pi:

```bash
cd ~/sonos-dial
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Test manually
python main.py
```

### 5. Install Service

```bash
sudo cp sonos-dial.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sonos-dial
sudo systemctl start sonos-dial
```

## Configuration

Edit `src/config.py`:

```python
# Sonos settings
VOLUME_STEP = 3  # Volume change per dial tick (percentage points)
ACTIVE_SPEAKER_POLL_INTERVAL = 5.0  # How often to check for active speaker

# Hue settings
HUE_ZONES = ["All Kitchen", "Stove Room", "Office"]  # Zones to cycle through
HUE_BRIGHTNESS_STEP = 25  # Brightness change per tick (0-254 scale)

# Device name pattern to match the dial
DIAL_DEVICE_NAME_PATTERN = "Keyboard"
```

### First-Time Hue Setup

The Hue bridge is auto-discovered on your network. On first run:

1. Watch the logs: `ssh <user>@<host>.local "sudo journalctl -u sonos-dial -f"`
2. When you see "Press the Hue bridge button", press the physical button on your Hue bridge
3. Restart the service: `sudo systemctl restart sonos-dial`

Credentials are saved to `~/.sonos-dial-hue` and won't need to be re-entered.

## Usage

The service starts in Sonos mode by default. It automatically:

1. Discovers Sonos speakers and Hue bridge on the network
2. In Sonos mode, finds whichever speaker is currently playing
3. Routes dial input to the active device

**Quadruple-click** to switch between Sonos and Hue modes. Mode persists across restarts.

In Hue mode, **double-click** to cycle through configured zones. The selected zone flashes briefly to confirm.

## Useful Commands

```bash
# Check service status
sudo systemctl status sonos-dial

# View logs (live) - run on Pi or via SSH
journalctl -u sonos-dial -f

# View logs remotely (from dev machine)
ssh <user>@<host>.local "sudo journalctl -u sonos-dial -f"

# View recent logs
journalctl -u sonos-dial -n 50

# Restart service
sudo systemctl restart sonos-dial

# Stop service
sudo systemctl stop sonos-dial

# Redeploy after code changes (from dev machine)
./deploy.sh
ssh <user>@<host>.local "sudo systemctl restart sonos-dial"
```

## Troubleshooting

### Dial not detected

```bash
# Check if dial receiver is connected
cat /proc/bus/input/devices

# Should see "LiQi Technology USB Composite Device Keyboard"
```

### Permission denied on /dev/input

```bash
# Add user to input group
sudo usermod -a -G input $USER
# Then reboot
```

### No Sonos speakers found

```bash
# Test discovery manually
cd ~/sonos-dial
source .venv/bin/activate
python -c "import soco; print(list(soco.discover()))"
```

Make sure the Pi is on the same network/VLAN as your Sonos speakers.

### Service won't start

```bash
# Check logs for errors
journalctl -u sonos-dial -n 100

# Try running manually to see errors
cd ~/sonos-dial
source .venv/bin/activate
python main.py
```

## Development

### Local Testing (without dial hardware)

```bash
# Run with mock input (reads +/-/p from stdin)
python src/main.py --mock
```

### Deploy Changes

```bash
# Edit code locally, then:
./deploy.sh
ssh <user>@<host>.local "sudo systemctl restart sonos-dial"
```

## Files

```
sonos-dial/
├── src/
│   ├── main.py           # Entry point, async controller
│   ├── dial_input.py     # evdev input handling, click detection
│   ├── sonos_control.py  # SoCo wrapper for Sonos
│   ├── hue_control.py    # phue wrapper for Hue
│   └── config.py         # Settings
├── requirements.txt      # Python dependencies
├── deploy.sh             # rsync to Pi
├── sonos-dial.service    # systemd unit file
└── README.md
```

### Persisted State

- `~/.sonos-dial-last-speaker` - Last active Sonos speaker
- `~/.sonos-dial-mode` - Current mode (sonos/hue)
- `~/.sonos-dial-hue-zone` - Last selected Hue zone
- `~/.sonos-dial-hue` - Hue bridge credentials

## Credits

- [SoCo](https://github.com/SoCo/SoCo) - Python library for Sonos control
- [phue](https://github.com/studioimaginaire/phue) - Python library for Philips Hue
- [python-evdev](https://python-evdev.readthedocs.io/) - Linux input device handling

Co-created with Claude Code.
