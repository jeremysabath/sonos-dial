"""Sonos control using the SoCo library."""

import soco
from soco import SoCo
from typing import Optional
import logging

from config import VOLUME_STEP

logger = logging.getLogger(__name__)


def discover_speakers() -> list[SoCo]:
    """Discover all Sonos speakers on the network."""
    speakers = soco.discover(timeout=5)
    if speakers is None:
        return []
    return sorted(list(speakers), key=lambda s: s.player_name)


def get_active_speaker(speakers: list[SoCo]) -> Optional[SoCo]:
    """
    Find the first speaker that is currently playing.
    Returns the group coordinator if the speaker is part of a group.
    """
    for speaker in speakers:
        try:
            transport_info = speaker.get_current_transport_info()
            state = transport_info.get("current_transport_state", "")

            if state == "PLAYING":
                # Return the group coordinator (controls the whole group)
                coordinator = speaker.group.coordinator
                logger.info(f"Found active speaker: {coordinator.player_name}")
                return coordinator
        except Exception as e:
            logger.debug(f"Error checking speaker {speaker.player_name}: {e}")
            continue

    return None


def adjust_volume(speaker: SoCo, delta: int = VOLUME_STEP) -> Optional[int]:
    """
    Adjust the group volume by delta percentage points.
    Returns the new volume level, or None on error.
    """
    try:
        current = speaker.group.volume
        new_volume = max(0, min(100, current + delta))
        speaker.group.volume = new_volume
        logger.info(f"Volume: {current} -> {new_volume}")
        return new_volume
    except Exception as e:
        logger.error(f"Error adjusting volume: {e}")
        return None


def toggle_playback(speaker: SoCo) -> Optional[str]:
    """
    Toggle play/pause on the speaker.
    Returns the new state ('PLAYING' or 'PAUSED_PLAYBACK'), or None on error.
    """
    try:
        transport_info = speaker.get_current_transport_info()
        state = transport_info.get("current_transport_state", "")

        if state == "PLAYING":
            speaker.pause()
            logger.info("Paused playback")
            return "PAUSED_PLAYBACK"
        else:
            speaker.play()
            logger.info("Started playback")
            return "PLAYING"
    except Exception as e:
        logger.error(f"Error toggling playback: {e}")
        return None
