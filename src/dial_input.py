"""Read input events from the Peakzooc dial via evdev."""

import asyncio
import logging
import time
from typing import Callable, Optional

try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False

from config import DIAL_DEVICE_NAME_PATTERN

logger = logging.getLogger(__name__)

# Multi-click detection settings
CLICK_DEBOUNCE = 0.30  # max time between clicks in a sequence (slightly generous to catch fast clickers)
MAX_CLICKS = 4  # maximum clicks to detect (4 = mode switch)


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

    Click detection:
    - Single click: play/pause
    - Double click: next track
    - Triple click: previous track
    """

    def __init__(
        self,
        on_volume_up: Callable[[], None],
        on_volume_down: Callable[[], None],
        on_press: Callable[[], None],
        on_double_press: Optional[Callable[[], None]] = None,
        on_triple_press: Optional[Callable[[], None]] = None,
        on_wiggle: Optional[Callable[[], None]] = None,
    ):
        self.on_volume_up = on_volume_up
        self.on_volume_down = on_volume_down
        self.on_press = on_press
        self.on_double_press = on_double_press
        self.on_triple_press = on_triple_press
        self.on_quadruple_press = on_wiggle  # Quadruple click for mode switch
        self._device: Optional[InputDevice] = None
        self._running = False
        self._click_count = 0
        self._last_click_time = 0.0
        self._click_task: Optional[asyncio.Task] = None

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

                # Only handle key press events (value=1), not release or hold
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
            self._handle_click()
        else:
            logger.debug(f"Dial: unknown key code {code}")

    def _handle_click(self):
        """Handle a click with multi-click detection using debounce."""
        now = time.time()
        time_since_last = now - self._last_click_time

        # If within debounce window of last click, it's part of the same sequence
        if time_since_last < CLICK_DEBOUNCE:
            self._click_count += 1
            logger.debug(f"Click {self._click_count} (gap: {time_since_last:.3f}s)")
        else:
            self._click_count = 1
            logger.debug(f"Click 1 (new sequence, gap: {time_since_last:.3f}s)")

        self._last_click_time = now

        # Cancel any pending click resolution
        if self._click_task and not self._click_task.done():
            self._click_task.cancel()
            logger.debug("Cancelled pending resolution")

        # If we've reached max clicks, resolve immediately (no waiting)
        if self._click_count >= MAX_CLICKS:
            logger.debug(f"Max clicks reached ({self._click_count}), resolving immediately")
            self._resolve_clicks()
        else:
            # Wait for debounce period to see if more clicks come
            self._click_task = asyncio.create_task(self._delayed_resolve())

    async def _delayed_resolve(self):
        """Wait for debounce period, then resolve."""
        await asyncio.sleep(CLICK_DEBOUNCE)
        self._resolve_clicks()

    def _resolve_clicks(self):
        """Execute the appropriate callback based on click count."""
        count = self._click_count
        self._click_count = 0

        if count == 1:
            logger.debug("Dial: single click -> play/pause")
            self.on_press()
        elif count == 2 and self.on_double_press:
            logger.debug("Dial: double click -> next")
            self.on_double_press()
        elif count == 3 and self.on_triple_press:
            logger.debug("Dial: triple click -> previous")
            self.on_triple_press()
        elif count >= 4 and self.on_quadruple_press:
            logger.debug("Dial: quadruple click -> mode switch")
            self.on_quadruple_press()
        else:
            # Fallback to single press if no handler
            logger.debug(f"Dial: {count} clicks, falling back to single press")
            self.on_press()

    def stop(self):
        """Stop the event loop by closing the device."""
        self._running = False
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass


class MockDialInputHandler:
    """
    Mock dial handler for local development without hardware.
    Reads from stdin: '+' for volume up, '-' for volume down, 'p' for press.
    Supports multi-click: type 'p' multiple times quickly, or '2'/'3'/'4' for double/triple/quadruple.
    """

    def __init__(
        self,
        on_volume_up: Callable[[], None],
        on_volume_down: Callable[[], None],
        on_press: Callable[[], None],
        on_double_press: Optional[Callable[[], None]] = None,
        on_triple_press: Optional[Callable[[], None]] = None,
        on_wiggle: Optional[Callable[[], None]] = None,
    ):
        self.on_volume_up = on_volume_up
        self.on_volume_down = on_volume_down
        self.on_press = on_press
        self.on_double_press = on_double_press
        self.on_triple_press = on_triple_press
        self.on_quadruple_press = on_wiggle  # Quadruple click for mode switch
        self._running = False
        self._click_count = 0
        self._last_click_time = 0.0
        self._click_task: Optional[asyncio.Task] = None

    def connect(self) -> bool:
        """Always returns True for mock."""
        return True

    async def run(self):
        """Run mock input loop reading from stdin."""
        self._running = True
        logger.info("Starting MOCK dial input (use +/-/p, or 2/3/4 for double/triple/quadruple click)")

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
                    self._handle_click()
                elif char == '2':
                    logger.debug("Mock: double press (shortcut)")
                    if self.on_double_press:
                        self.on_double_press()
                elif char == '3':
                    logger.debug("Mock: triple press (shortcut)")
                    if self.on_triple_press:
                        self.on_triple_press()
                elif char == '4':
                    logger.debug("Mock: quadruple press (shortcut)")
                    if self.on_quadruple_press:
                        self.on_quadruple_press()

        except Exception as e:
            logger.error(f"Error in mock input loop: {e}")
        finally:
            self._running = False

    def _handle_click(self):
        """Handle a click with multi-click detection using debounce."""
        now = time.time()

        if now - self._last_click_time < CLICK_DEBOUNCE:
            self._click_count += 1
        else:
            self._click_count = 1

        self._last_click_time = now

        if self._click_task and not self._click_task.done():
            self._click_task.cancel()

        if self._click_count >= MAX_CLICKS:
            self._resolve_clicks()
        else:
            self._click_task = asyncio.create_task(self._delayed_resolve())

    async def _delayed_resolve(self):
        """Wait for debounce period, then resolve."""
        await asyncio.sleep(CLICK_DEBOUNCE)
        self._resolve_clicks()

    def _resolve_clicks(self):
        """Execute the appropriate callback based on click count."""
        count = self._click_count
        self._click_count = 0

        if count == 1:
            logger.debug("Mock: single press -> play/pause")
            self.on_press()
        elif count == 2 and self.on_double_press:
            logger.debug("Mock: double press -> next")
            self.on_double_press()
        elif count == 3 and self.on_triple_press:
            logger.debug("Mock: triple press -> previous")
            self.on_triple_press()
        elif count >= 4 and self.on_quadruple_press:
            logger.debug("Mock: quadruple press -> mode switch")
            self.on_quadruple_press()
        else:
            logger.debug(f"Mock: {count} clicks, falling back to single press")
            self.on_press()

    def stop(self):
        """Stop the event loop."""
        self._running = False
