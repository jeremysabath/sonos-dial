# Sonos Dial Controller

A Raspberry Pi Zero 2W project that turns a Peakzooc wireless dial into a physical Sonos controller.

- **Rotate dial**: Adjust volume
- **Press dial**: Play/pause
- **Auto-selects**: Controls whichever speaker is currently playing

## Hardware

- Raspberry Pi Zero 2W
- Peakzooc desktop volume knob (2.4G wireless version)
- Micro-USB OTG adapter (Pi Zero's data port is micro-USB, dial receiver is USB-A)
- USB-C power supply for the Pi
- MicroSD card (8GB+)

## Architecture

```
[Dial] --2.4G USB--> [Pi Zero 2W] --WiFi--> [Sonos Speakers]
                          |
                     Python service
                     (evdev + soco)
```

The dial presents as a USB HID keyboard, sending `KEY_VOLUMEUP`, `KEY_VOLUMEDOWN`, and `KEY_MUTE` events. The Python service reads these via `evdev` and translates them to Sonos API calls via `soco`.

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
# Volume change per dial tick (percentage points)
VOLUME_STEP = 3

# How often to check for active speaker (seconds)
ACTIVE_SPEAKER_POLL_INTERVAL = 5.0

# Device name pattern to match the dial
DIAL_DEVICE_NAME_PATTERN = "Keyboard"
```

## Usage

Just turn the dial. The service automatically:

1. Discovers all Sonos speakers on the network
2. Finds whichever one is currently playing
3. Routes dial input to that speaker's group

If nothing is playing, dial input is ignored.

## Useful Commands

```bash
# Check service status
sudo systemctl status sonos-dial

# View logs (live)
journalctl -u sonos-dial -f

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
│   ├── dial_input.py     # evdev input handling
│   ├── sonos_control.py  # SoCo wrapper
│   └── config.py         # Settings
├── requirements.txt      # Python dependencies
├── deploy.sh             # rsync to Pi
├── sonos-dial.service    # systemd unit file
└── README.md
```

## Credits

- [SoCo](https://github.com/SoCo/SoCo) - Python library for Sonos control
- [python-evdev](https://python-evdev.readthedocs.io/) - Linux input device handling

Co-created with Claude Code.
