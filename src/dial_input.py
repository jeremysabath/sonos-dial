"""Read input events from the Peakzooc dial via evdev."""

import asyncio
import logging
from typing import Callable, Optional

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False

from config import DIAL_DEVICE_NAME_PATTERN

logger = logging.getLogger(__name__)


def find_dial_device() -> Optional[str]:
    """
    Find the dial input device by name pattern.
    Returns the device path (e.g., /dev/input/event0) or None if not found.
    """
    if not EVDEV_AVAILABLE:
        logger.warning("evdev not available - dial input disabled")
        return None

    for path in evdev.list_devices():
        try:
            device = InputDevice(path)
            if DIAL_DEVICE_NAME_PATTERN.lower() in device.name.lower():
                logger.info(f"Found dial device: {device.name} at {path}")
                return path
        except Exception as e:
            logger.debug(f"Error checking device {path}: {e}")
            continue

    logger.warning(f"No device matching '{DIAL_DEVICE_NAME_PATTERN}' found")
    return None


class DialInputHandler:
    """
    Async handler for dial input events.

    The Peakzooc dial sends media key events:
    - KEY_VOLUMEUP (115): rotate right
    - KEY_VOLUMEDOWN (114): rotate left
    - KEY_MUTE (113): press/click
    """

    def __init__(
        self,
        on_volume_up: Callable[[], None],
        on_volume_down: Callable[[], None],
        on_press: Callable[[], None],
    ):
        self.on_volume_up = on_volume_up
        self.on_volume_down = on_volume_down
        self.on_press = on_press
        self._device: Optional[InputDevice] = None
        self._running = False

    def connect(self) -> bool:
        """
        Connect to the dial device.
        Returns True if successful, False otherwise.
        """
        if not EVDEV_AVAILABLE:
            return False

        device_path = find_dial_device()
        if device_path is None:
            return False

        try:
            self._device = InputDevice(device_path)
            logger.info(f"Connected to dial: {self._device.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to dial: {e}")
            return False

    async def run(self):
        """
        Start the async event loop for reading dial input.
        Runs until stopped or device disconnects.
        """
        if self._device is None:
            if not self.connect():
                logger.error("Cannot run without connected device")
                return

        self._running = True
        logger.info("Starting dial input loop")

        try:
            async for event in self._device.async_read_loop():
                if not self._running:
                    break

                # Only handle key press events (value=1), not release (value=0) or hold (value=2)
                if event.type == ecodes.EV_KEY and event.value == 1:
                    self._handle_key(event.code)

        except Exception as e:
            logger.error(f"Error in dial input loop: {e}")
        finally:
            self._running = False
            logger.info("Dial input loop stopped")

    def _handle_key(self, code: int):
        """Handle a key press event."""
        if code == ecodes.KEY_VOLUMEUP:
            logger.debug("Dial: volume up")
            self.on_volume_up()
        elif code == ecodes.KEY_VOLUMEDOWN:
            logger.debug("Dial: volume down")
            self.on_volume_down()
        elif code == ecodes.KEY_MUTE:
            logger.debug("Dial: press")
            self.on_press()
        else:
            logger.debug(f"Dial: unknown key code {code}")

    def stop(self):
        """Stop the event loop."""
        self._running = False


class MockDialInputHandler:
    """
    Mock dial handler for local development without hardware.
    Reads from stdin: '+' for volume up, '-' for volume down, 'p' for press.
    """

    def __init__(
        self,
        on_volume_up: Callable[[], None],
        on_volume_down: Callable[[], None],
        on_press: Callable[[], None],
    ):
        self.on_volume_up = on_volume_up
        self.on_volume_down = on_volume_down
        self.on_press = on_press
        self._running = False

    def connect(self) -> bool:
        """Always returns True for mock."""
        return True

    async def run(self):
        """Run mock input loop reading from stdin."""
        self._running = True
        logger.info("Starting MOCK dial input loop (use +/-/p keys)")

        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        try:
            await loop.connect_read_pipe(lambda: protocol, __import__('sys').stdin)

            while self._running:
                line = await reader.readline()
                if not line:
                    break

                char = line.decode().strip()
                if char == '+':
                    logger.debug("Mock: volume up")
                    self.on_volume_up()
                elif char == '-':
                    logger.debug("Mock: volume down")
                    self.on_volume_down()
                elif char == 'p':
                    logger.debug("Mock: press")
                    self.on_press()

        except Exception as e:
            logger.error(f"Error in mock input loop: {e}")
        finally:
            self._running = False

    def stop(self):
        """Stop the event loop."""
        self._running = False
