#!/usr/bin/env python3
"""
Sonos Dial Controller

A simple service that connects a Peakzooc dial to Sonos speakers.
- Dial rotation: volume control
- Dial press: play/pause
- Auto-selects the currently playing speaker/group
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from config import VOLUME_STEP, ACTIVE_SPEAKER_POLL_INTERVAL
from sonos_control import discover_speakers, get_active_speaker, adjust_volume, toggle_playback
from dial_input import DialInputHandler, MockDialInputHandler, EVDEV_AVAILABLE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class SonosDialController:
    """Main controller that ties dial input to Sonos control."""

    def __init__(self, use_mock_dial: bool = False):
        self.speakers = []
        self.active_speaker = None
        self._last_speaker = None  # Remember last controlled speaker
        self._running = False
        self._use_mock_dial = use_mock_dial

        # Create dial handler with callbacks
        handler_class = MockDialInputHandler if use_mock_dial else DialInputHandler
        self.dial = handler_class(
            on_volume_up=self._on_volume_up,
            on_volume_down=self._on_volume_down,
            on_press=self._on_press,
        )

    def _get_target_speaker(self):
        """Get the speaker to control: active speaker, or last known speaker."""
        return self.active_speaker or self._last_speaker

    def _on_volume_up(self):
        """Handle dial rotation clockwise."""
        speaker = self._get_target_speaker()
        if speaker:
            adjust_volume(speaker, VOLUME_STEP)
        else:
            logger.debug("No speaker to control, ignoring volume up")

    def _on_volume_down(self):
        """Handle dial rotation counter-clockwise."""
        speaker = self._get_target_speaker()
        if speaker:
            adjust_volume(speaker, -VOLUME_STEP)
        else:
            logger.debug("No speaker to control, ignoring volume down")

    def _on_press(self):
        """Handle dial press."""
        speaker = self._get_target_speaker()
        if speaker:
            toggle_playback(speaker)
        else:
            logger.debug("No speaker to control, ignoring press")

    async def _poll_active_speaker(self):
        """Periodically check for active speaker."""
        while self._running:
            try:
                # Re-discover speakers periodically in case network changed
                self.speakers = discover_speakers()
                if not self.speakers:
                    logger.warning("No Sonos speakers found on network")
                    self.active_speaker = None
                else:
                    self.active_speaker = get_active_speaker(self.speakers)
                    if self.active_speaker:
                        # Remember this speaker for when playback stops
                        self._last_speaker = self.active_speaker
                    elif self._last_speaker:
                        logger.debug(f"No speaker playing, using last: {self._last_speaker.player_name}")
                    else:
                        logger.debug("No speaker currently playing")

            except Exception as e:
                logger.error(f"Error polling speakers: {e}")

            await asyncio.sleep(ACTIVE_SPEAKER_POLL_INTERVAL)

    async def run(self):
        """Start the controller."""
        self._running = True
        logger.info("Starting Sonos Dial Controller")

        # Initial discovery
        logger.info("Discovering Sonos speakers...")
        self.speakers = discover_speakers()
        if self.speakers:
            logger.info(f"Found {len(self.speakers)} speaker(s): {[s.player_name for s in self.speakers]}")
        else:
            logger.warning("No Sonos speakers found - will keep trying")

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


def main():
    # Check for mock mode (for local development without dial hardware)
    use_mock = "--mock" in sys.argv or not EVDEV_AVAILABLE

    if use_mock and "--mock" not in sys.argv:
        logger.info("evdev not available, using mock dial input")

    controller = SonosDialController(use_mock_dial=use_mock)

    # Handle signals for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        controller.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the controller
    try:
        asyncio.run(controller.run())
    except KeyboardInterrupt:
        pass

    logger.info("Goodbye!")


if __name__ == "__main__":
    main()
