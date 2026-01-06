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


def next_track(speaker: SoCo) -> bool:
    """
    Skip to the next track.
    Returns True on success, False on error.
    """
    try:
        speaker.next()
        logger.info("Skipped to next track")
        return True
    except Exception as e:
        logger.error(f"Error skipping to next track: {e}")
        return False


def previous_track(speaker: SoCo, restart_threshold: int = 3) -> bool:
    """
    Go back to the previous track (or restart current track if mid-playback).
    Standard media behavior: if more than threshold seconds into track, restart; otherwise go to previous.
    Returns True on success, False on error.
    """
    try:
        # Get current position in track
        track_info = speaker.get_current_track_info()
        position = track_info.get("position", "0:00:00")

        # Parse position (format: H:MM:SS or HH:MM:SS)
        parts = position.split(":")
        seconds = int(parts[-1]) + int(parts[-2]) * 60
        if len(parts) > 2:
            seconds += int(parts[-3]) * 3600

        if seconds > restart_threshold:
            # Mid-track: restart current track
            speaker.seek("0:00:00")
            logger.info(f"Restarted track (was at {position})")
        else:
            # Near start: go to previous track
            speaker.previous()
            logger.info(f"Previous track (was at {position})")
        return True
    except Exception as e:
        logger.error(f"Error in previous_track: {e}")
        return False
