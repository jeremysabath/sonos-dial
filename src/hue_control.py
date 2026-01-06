"""Philips Hue control using the phue library."""

import json
import logging
import urllib.request
from typing import Optional

try:
    from phue import Bridge, PhueRegistrationException
    PHUE_AVAILABLE = True
except ImportError:
    PHUE_AVAILABLE = False
    Bridge = None
    PhueRegistrationException = Exception

from config import HUE_CONFIG_FILE, HUE_BRIDGE_IP

logger = logging.getLogger(__name__)


def discover_bridge() -> Optional[str]:
    """
    Discover Hue bridge on the network.

    Uses the Philips discovery service (https://discovery.meethue.com).
    Returns bridge IP or None if not found.
    """
    # Use configured IP if set
    if HUE_BRIDGE_IP:
        logger.info(f"Using configured Hue bridge IP: {HUE_BRIDGE_IP}")
        return HUE_BRIDGE_IP

    if not PHUE_AVAILABLE:
        logger.warning("phue not available - Hue control disabled")
        return None

    try:
        with urllib.request.urlopen("https://discovery.meethue.com", timeout=5) as response:
            data = json.loads(response.read().decode())
            if data and len(data) > 0:
                bridge_ip = data[0].get("internalipaddress")
                logger.info(f"Discovered Hue bridge at {bridge_ip}")
                return bridge_ip
    except urllib.error.URLError as e:
        logger.debug(f"Hue bridge discovery failed (network error): {e}")
    except json.JSONDecodeError as e:
        logger.debug(f"Hue bridge discovery failed (invalid response): {e}")
    except Exception as e:
        logger.debug(f"Hue bridge discovery failed: {e}")

    logger.warning("No Hue bridge found on network")
    return None


def connect_bridge(ip: str, config_path: str = HUE_CONFIG_FILE) -> Optional[Bridge]:
    """
    Connect to Hue bridge at given IP.

    On first connection, user must press the bridge button.
    Credentials are saved to config_path for future use.

    Returns Bridge object or None on failure.
    Raises PhueRegistrationException if pairing is required.
    """
    if not PHUE_AVAILABLE:
        return None

    try:
        bridge = Bridge(ip, config_file_path=config_path)
        bridge.connect()
        logger.info(f"Connected to Hue bridge at {ip}")
        return bridge
    except PhueRegistrationException:
        logger.warning("Hue pairing required - press the bridge button and restart")
        raise
    except Exception as e:
        logger.error(f"Failed to connect to Hue bridge: {e}")
        return None


def get_zones(bridge: Bridge) -> list[dict]:
    """
    Get all zones/rooms from the bridge.
    Returns list of dicts with 'id', 'name', and 'lights' keys.
    """
    if not bridge:
        return []

    try:
        groups = bridge.get_group()
        zones = []
        for group_id, group_data in groups.items():
            zones.append({
                "id": group_id,
                "name": group_data.get("name", f"Group {group_id}"),
                "lights": group_data.get("lights", []),
            })
        return zones
    except Exception as e:
        logger.error(f"Error getting zones: {e}")
        return []


def toggle_zone(bridge: Bridge, zone_name: str) -> Optional[bool]:
    """
    Toggle all lights in a zone on/off.
    Returns new state (True=on, False=off) or None on error.
    """
    if not bridge:
        return None

    try:
        groups = bridge.get_group()
        for group_id, group_data in groups.items():
            if group_data.get("name", "").lower() == zone_name.lower():
                current_on = group_data.get("action", {}).get("on", False)
                new_state = not current_on
                bridge.set_group(int(group_id), "on", new_state)
                logger.debug(f"Zone '{zone_name}' turned {'on' if new_state else 'off'}")
                return new_state
        logger.warning(f"Zone '{zone_name}' not found for toggle")
        return None
    except Exception as e:
        logger.error(f"Error toggling zone: {e}")
        return None


def adjust_brightness(bridge: Bridge, zone_name: str, delta: int) -> Optional[int]:
    """
    Adjust brightness of a zone by delta (on 0-254 scale).
    Turns lights on if they're off.
    Returns new brightness or None on error.
    """
    if not bridge:
        return None

    try:
        groups = bridge.get_group()
        for group_id, group_data in groups.items():
            if group_data.get("name", "").lower() == zone_name.lower():
                action = group_data.get("action", {})
                current_bri = action.get("bri", 127)
                is_on = action.get("on", False)

                new_bri = max(1, min(254, current_bri + delta))

                # If turning up brightness and lights are off, turn them on
                if not is_on and delta > 0:
                    bridge.set_group(int(group_id), {"on": True, "bri": new_bri})
                    logger.debug(f"Zone '{zone_name}' turned on, brightness: {new_bri}")
                # If turning down to minimum, turn off
                elif new_bri <= 1 and delta < 0:
                    bridge.set_group(int(group_id), "on", False)
                    logger.debug(f"Zone '{zone_name}' turned off (brightness at minimum)")
                    return 0
                else:
                    bridge.set_group(int(group_id), "bri", new_bri)
                    logger.debug(f"Zone '{zone_name}' brightness: {current_bri} -> {new_bri}")

                return new_bri

        logger.warning(f"Zone '{zone_name}' not found for brightness adjustment")
        return None
    except Exception as e:
        logger.error(f"Error adjusting brightness: {e}")
        return None


def flash_zone(bridge: Bridge, zone_name: str) -> bool:
    """
    Brief flash of lights in zone (for mode switch feedback).
    Uses the Hue 'alert' feature for a single flash.
    Returns True on success.
    """
    if not bridge:
        return False

    try:
        groups = bridge.get_group()
        for group_id, group_data in groups.items():
            if group_data.get("name", "").lower() == zone_name.lower():
                bridge.set_group(int(group_id), "alert", "select")
                logger.debug(f"Flashed zone '{zone_name}'")
                return True
        logger.warning(f"Zone '{zone_name}' not found for flash")
        return False
    except Exception as e:
        logger.error(f"Error flashing zone: {e}")
        return False
