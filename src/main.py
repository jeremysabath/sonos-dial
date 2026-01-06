#!/usr/bin/env python3
"""
Sonos Dial Controller

A simple service that connects a Peakzooc dial to Sonos speakers.
- Dial rotation: volume control
- Single click: play/pause
- Double click: next track
- Triple click: previous track
- Auto-selects the currently playing speaker/group
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Optional

from config import VOLUME_STEP, ACTIVE_SPEAKER_POLL_INTERVAL, HUE_ZONES, HUE_BRIGHTNESS_STEP
from sonos_control import discover_speakers, get_active_speaker, adjust_volume, toggle_playback, next_track, previous_track
from hue_control import discover_bridge, connect_bridge, toggle_zone, adjust_brightness, PHUE_AVAILABLE

# File to persist last speaker across restarts
LAST_SPEAKER_FILE = os.path.expanduser("~/.sonos-dial-last-speaker")
# File to persist mode across restarts
MODE_FILE = os.path.expanduser("~/.sonos-dial-mode")
# File to persist last Hue zone across restarts
HUE_ZONE_FILE = os.path.expanduser("~/.sonos-dial-hue-zone")
from dial_input import DialInputHandler, MockDialInputHandler, EVDEV_AVAILABLE

# Configure logging (--debug flag enables DEBUG level)
log_level = logging.DEBUG if "--debug" in sys.argv else logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Dry-run mode: log actions without making API calls
DRY_RUN = "--dry-run" in sys.argv


class SonosDialController:
    """Main controller that ties dial input to Sonos control."""

    def __init__(self, use_mock_dial: bool = False):
        self.speakers = []
        self.active_speaker = None
        self._last_speaker = None  # Remember last controlled speaker
        self._last_speaker_name = None  # Persisted name for recovery
        self._running = False
        self._use_mock_dial = use_mock_dial
        self._load_last_speaker_name()

        # Mode state: "sonos" or "hue"
        self._mode = "sonos"
        self._load_mode()

        # Hue state
        self._hue_bridge = None
        self._hue_zone = HUE_ZONES[0]  # Default to first zone
        self._load_hue_zone()
        self._hue_brightness_delta = 0  # Accumulated brightness change
        self._hue_brightness_task: Optional[asyncio.Task] = None
        self._hue_last_send_time = 0.0  # For throttling

        # Sonos volume throttling state (prevents race conditions with rapid dial turns)
        self._sonos_volume_delta = 0  # Accumulated volume change
        self._sonos_volume_task: Optional[asyncio.Task] = None
        self._sonos_last_send_time = 0.0  # For throttling

        # Create dial handler with callbacks
        handler_class = MockDialInputHandler if use_mock_dial else DialInputHandler
        self.dial = handler_class(
            on_volume_up=self._on_volume_up,
            on_volume_down=self._on_volume_down,
            on_press=self._on_press,
            on_double_press=self._on_double_press,
            on_triple_press=self._on_triple_press,
            on_wiggle=self._on_wiggle,
        )

    def _load_last_speaker_name(self):
        """Load persisted speaker name from disk."""
        try:
            if os.path.exists(LAST_SPEAKER_FILE):
                with open(LAST_SPEAKER_FILE, 'r') as f:
                    self._last_speaker_name = f.read().strip()
                    if self._last_speaker_name:
                        logger.info(f"Loaded last speaker from disk: {self._last_speaker_name}")
        except Exception as e:
            logger.debug(f"Could not load last speaker: {e}")

    def _save_last_speaker_name(self, name: str):
        """Persist speaker name to disk."""
        try:
            with open(LAST_SPEAKER_FILE, 'w') as f:
                f.write(name)
            self._last_speaker_name = name
        except Exception as e:
            logger.debug(f"Could not save last speaker: {e}")

    def _load_mode(self):
        """Load persisted mode from disk."""
        try:
            if os.path.exists(MODE_FILE):
                with open(MODE_FILE, 'r') as f:
                    mode = f.read().strip()
                    if mode in ("sonos", "hue"):
                        self._mode = mode
                        logger.info(f"Loaded mode from disk: {self._mode}")
        except Exception as e:
            logger.debug(f"Could not load mode: {e}")

    def _save_mode(self):
        """Persist current mode to disk."""
        try:
            with open(MODE_FILE, 'w') as f:
                f.write(self._mode)
        except Exception as e:
            logger.debug(f"Could not save mode: {e}")

    def _load_hue_zone(self):
        """Load persisted Hue zone from disk."""
        try:
            if os.path.exists(HUE_ZONE_FILE):
                with open(HUE_ZONE_FILE, 'r') as f:
                    zone = f.read().strip()
                    if zone in HUE_ZONES:
                        self._hue_zone = zone
                        logger.info(f"Loaded Hue zone from disk: {self._hue_zone}")
        except Exception as e:
            logger.debug(f"Could not load Hue zone: {e}")

    def _save_hue_zone(self):
        """Persist current Hue zone to disk."""
        try:
            with open(HUE_ZONE_FILE, 'w') as f:
                f.write(self._hue_zone)
        except Exception as e:
            logger.debug(f"Could not save Hue zone: {e}")

    def _get_target_speaker(self):
        """Get the speaker to control: active speaker, or last known speaker."""
        return self.active_speaker or self._last_speaker

    def _on_volume_up(self):
        """Handle dial rotation clockwise."""
        if self._mode == "sonos":
            self._sonos_volume_up()
        else:
            self._hue_brightness_up()

    def _on_volume_down(self):
        """Handle dial rotation counter-clockwise."""
        if self._mode == "sonos":
            self._sonos_volume_down()
        else:
            self._hue_brightness_down()

    def _on_press(self):
        """Handle dial single press."""
        if self._mode == "sonos":
            self._sonos_toggle_playback()
        else:
            self._hue_toggle()

    def _on_double_press(self):
        """Handle dial double press -> next track (Sonos) or next zone (Hue)."""
        if self._mode == "sonos":
            speaker = self._get_target_speaker()
            if speaker:
                next_track(speaker)
            else:
                logger.debug("No speaker to control, ignoring double press")
        else:
            self._hue_next_zone()

    def _on_triple_press(self):
        """Handle dial triple press -> previous track (Sonos only)."""
        if self._mode == "sonos":
            speaker = self._get_target_speaker()
            if speaker:
                previous_track(speaker)
            else:
                logger.debug("No speaker to control, ignoring triple press")

    def _on_wiggle(self):
        """Handle quadruple click -> toggle mode."""
        logger.debug("Quadruple click detected")
        old_mode = self._mode
        self._mode = "hue" if self._mode == "sonos" else "sonos"
        self._save_mode()
        logger.info(f"Mode switched: {old_mode} -> {self._mode}")

        # Flash all Hue zones for feedback
        if self._hue_bridge:
            if self._mode == "hue":
                # Sonos -> Hue: double flash
                asyncio.create_task(self._flash_all_zones(count=2))
            else:
                # Hue -> Sonos: single flash
                asyncio.create_task(self._flash_all_zones(count=1))
        else:
            logger.warning("No Hue bridge connected, cannot flash")

    # Sonos-specific handlers

    def _sonos_volume_up(self):
        """Sonos: increase volume (throttled)."""
        speaker = self._get_target_speaker()
        if speaker:
            self._queue_sonos_volume(VOLUME_STEP)
        else:
            logger.debug("No speaker to control, ignoring volume up")

    def _sonos_volume_down(self):
        """Sonos: decrease volume (throttled)."""
        speaker = self._get_target_speaker()
        if speaker:
            self._queue_sonos_volume(-VOLUME_STEP)
        else:
            logger.debug("No speaker to control, ignoring volume down")

    def _queue_sonos_volume(self, delta: int):
        """Accumulate volume delta with throttling (max ~7 updates/sec)."""
        import time
        self._sonos_volume_delta += delta
        now = time.time()
        throttle_interval = 0.15  # 150ms between sends

        # If enough time passed, send immediately
        if now - self._sonos_last_send_time >= throttle_interval:
            self._sonos_last_send_time = now
            accumulated = self._sonos_volume_delta
            self._sonos_volume_delta = 0
            asyncio.create_task(self._send_sonos_volume(accumulated))
        else:
            # Schedule trailing send to catch final value
            if self._sonos_volume_task and not self._sonos_volume_task.done():
                self._sonos_volume_task.cancel()
            self._sonos_volume_task = asyncio.create_task(self._trailing_sonos_volume())

    async def _send_sonos_volume(self, delta: int):
        """Send volume adjustment to Sonos speaker."""
        speaker = self._get_target_speaker()
        if speaker:
            if DRY_RUN:
                logger.info(f"[DRY-RUN] Would adjust volume by {delta:+d} on {speaker.player_name}")
                return
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, adjust_volume, speaker, delta)

    async def _trailing_sonos_volume(self):
        """Wait then send any remaining accumulated volume."""
        import time
        await asyncio.sleep(0.15)

        if self._sonos_volume_delta != 0:
            self._sonos_last_send_time = time.time()
            delta = self._sonos_volume_delta
            self._sonos_volume_delta = 0
            await self._send_sonos_volume(delta)

    def _sonos_toggle_playback(self):
        """Sonos: toggle play/pause."""
        speaker = self._get_target_speaker()
        if speaker:
            toggle_playback(speaker)
        else:
            logger.debug("No speaker to control, ignoring press")

    # Hue-specific handlers

    def _hue_next_zone(self):
        """Cycle to the next Hue zone."""
        try:
            current_idx = HUE_ZONES.index(self._hue_zone)
            next_idx = (current_idx + 1) % len(HUE_ZONES)
        except ValueError:
            next_idx = 0

        old_zone = self._hue_zone
        self._hue_zone = HUE_ZONES[next_idx]
        self._save_hue_zone()
        logger.info(f"Hue zone changed: {old_zone} -> {self._hue_zone}")

        # Flash the new zone to confirm
        if self._hue_bridge:
            asyncio.create_task(self._flash_zone_change())

    async def _flash_zone_change(self):
        """Brief dim-then-brighten to indicate zone change."""
        loop = asyncio.get_event_loop()
        # Dim down
        await loop.run_in_executor(
            None, adjust_brightness, self._hue_bridge, self._hue_zone, -50
        )
        await asyncio.sleep(0.15)
        # Brighten back up
        await loop.run_in_executor(
            None, adjust_brightness, self._hue_bridge, self._hue_zone, 50
        )

    def _hue_brightness_up(self):
        """Hue: increase brightness (debounced)."""
        if self._hue_bridge:
            self._queue_hue_brightness(HUE_BRIGHTNESS_STEP)
        else:
            logger.debug("No Hue bridge connected, ignoring brightness up")

    def _hue_brightness_down(self):
        """Hue: decrease brightness (debounced)."""
        if self._hue_bridge:
            self._queue_hue_brightness(-HUE_BRIGHTNESS_STEP)
        else:
            logger.debug("No Hue bridge connected, ignoring brightness down")

    def _queue_hue_brightness(self, delta: int):
        """Accumulate brightness delta with throttling (max ~7 updates/sec)."""
        import time
        self._hue_brightness_delta += delta
        now = time.time()
        throttle_interval = 0.15  # 150ms between sends

        # If enough time passed, send immediately
        if now - self._hue_last_send_time >= throttle_interval:
            self._hue_last_send_time = now
            accumulated = self._hue_brightness_delta
            self._hue_brightness_delta = 0
            asyncio.create_task(self._send_hue_brightness(accumulated))
        else:
            # Schedule trailing send to catch final value
            if self._hue_brightness_task and not self._hue_brightness_task.done():
                self._hue_brightness_task.cancel()
            self._hue_brightness_task = asyncio.create_task(self._trailing_hue_brightness())

    def _hue_toggle(self):
        """Hue: toggle on/off."""
        if self._hue_bridge:
            asyncio.create_task(self._async_hue_toggle())
        else:
            logger.debug("No Hue bridge connected, ignoring toggle")

    async def _send_hue_brightness(self, delta: int):
        """Send brightness adjustment to Hue bridge."""
        if DRY_RUN:
            logger.info(f"[DRY-RUN] Would adjust Hue brightness by {delta:+d} on {self._hue_zone}")
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, adjust_brightness, self._hue_bridge, self._hue_zone, delta
        )

    async def _trailing_hue_brightness(self):
        """Wait then send any remaining accumulated brightness."""
        import time
        await asyncio.sleep(0.15)

        if self._hue_brightness_delta != 0:
            self._hue_last_send_time = time.time()
            delta = self._hue_brightness_delta
            self._hue_brightness_delta = 0
            await self._send_hue_brightness(delta)

    async def _async_hue_toggle(self):
        """Async wrapper for Hue toggle."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, toggle_zone, self._hue_bridge, self._hue_zone
        )

    async def _flash_all_zones(self, count: int = 1):
        """Flash all Hue zones for mode switch feedback."""
        loop = asyncio.get_event_loop()
        logger.debug(f"Flashing all zones {count}x: {HUE_ZONES}")

        for i in range(count):
            # Dim all zones simultaneously
            await asyncio.gather(*[
                loop.run_in_executor(
                    None, adjust_brightness, self._hue_bridge, zone, -50
                )
                for zone in HUE_ZONES
            ])
            await asyncio.sleep(0.15)
            # Brighten all zones simultaneously
            await asyncio.gather(*[
                loop.run_in_executor(
                    None, adjust_brightness, self._hue_bridge, zone, 50
                )
                for zone in HUE_ZONES
            ])
            if i < count - 1:
                await asyncio.sleep(0.08)  # Gap between flashes

    async def _poll_active_speaker(self):
        """Periodically check for active speaker."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                # Run blocking Sonos calls in thread pool with timeout
                self.speakers = await asyncio.wait_for(
                    loop.run_in_executor(None, discover_speakers),
                    timeout=10.0
                )
                if not self.speakers:
                    logger.warning("No Sonos speakers found on network")
                    self.active_speaker = None
                else:
                    self.active_speaker = await asyncio.wait_for(
                        loop.run_in_executor(None, get_active_speaker, self.speakers),
                        timeout=10.0
                    )
                    if self.active_speaker:
                        # Remember this speaker for when playback stops
                        self._last_speaker = self.active_speaker
                        self._save_last_speaker_name(self.active_speaker.player_name)
                    elif self._last_speaker:
                        logger.debug(f"No speaker playing, using last: {self._last_speaker.player_name}")
                    elif self._last_speaker_name and not self._last_speaker:
                        # Try to recover speaker from persisted name
                        for speaker in self.speakers:
                            if speaker.player_name == self._last_speaker_name:
                                self._last_speaker = speaker.group.coordinator
                                logger.info(f"Recovered last speaker from disk: {self._last_speaker.player_name}")
                                break
                    else:
                        logger.debug("No speaker currently playing")

            except asyncio.TimeoutError:
                logger.warning("Sonos polling timed out - will retry")
            except Exception as e:
                logger.error(f"Error polling speakers: {e}")

            await asyncio.sleep(ACTIVE_SPEAKER_POLL_INTERVAL)

    async def _initialize_hue(self):
        """Initialize Hue bridge connection."""
        if not PHUE_AVAILABLE:
            logger.info("phue not installed - Hue control disabled")
            return

        loop = asyncio.get_event_loop()

        # Discover bridge
        logger.info("Discovering Hue bridge...")
        bridge_ip = await loop.run_in_executor(None, discover_bridge)
        if not bridge_ip:
            logger.warning("No Hue bridge found - Hue control disabled")
            return

        # Connect to bridge
        try:
            self._hue_bridge = await loop.run_in_executor(
                None, connect_bridge, bridge_ip
            )
            if self._hue_bridge:
                logger.info(f"Hue bridge connected at {bridge_ip}, default zone: {self._hue_zone}")
        except Exception as e:
            logger.warning(f"Hue bridge pairing required: {e}")
            logger.info("Press the Hue bridge button and restart the service to pair")

    async def run(self):
        """Start the controller."""
        self._running = True
        logger.info("Starting Sonos Dial Controller")
        logger.info(f"Current mode: {self._mode}")

        loop = asyncio.get_event_loop()

        # Initial Sonos discovery (run in thread to not block, with timeout)
        logger.info("Discovering Sonos speakers...")
        try:
            self.speakers = await asyncio.wait_for(
                loop.run_in_executor(None, discover_speakers),
                timeout=15.0  # Don't let discovery hang startup
            )
            if self.speakers:
                logger.info(f"Found {len(self.speakers)} speaker(s): {[s.player_name for s in self.speakers]}")
            else:
                logger.warning("No Sonos speakers found - will keep trying")
        except asyncio.TimeoutError:
            logger.warning("Sonos discovery timed out - will keep trying in background")
            self.speakers = []

        # Initialize Hue
        await self._initialize_hue()

        # Connect to dial
        if not self.dial.connect():
            if not self._use_mock_dial:
                logger.error("Failed to connect to dial - is the 2.4G receiver plugged in?")
                return

        # Run dial input and speaker polling concurrently
        try:
            await asyncio.gather(
                self.dial.run(),
                self._poll_active_speaker(),
            )
        except asyncio.CancelledError:
            logger.info("Controller cancelled")
        finally:
            self._running = False
            self.dial.stop()
            logger.info("Controller stopped")

    def stop(self):
        """Stop the controller."""
        self._running = False
        self.dial.stop()


async def async_main():
    """Async entry point with proper signal handling."""
    # Check for mock mode (for local development without dial hardware)
    use_mock = "--mock" in sys.argv or not EVDEV_AVAILABLE

    if use_mock and "--mock" not in sys.argv:
        logger.info("evdev not available, using mock dial input")

    controller = SonosDialController(use_mock_dial=use_mock)
    main_task = None

    # Set up asyncio-compatible signal handlers
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Received shutdown signal, stopping...")
        controller.stop()
        # Cancel the main task to force immediate exit
        if main_task and not main_task.done():
            main_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        main_task = asyncio.current_task()
        await controller.run()
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    finally:
        logger.info("Goodbye!")


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
