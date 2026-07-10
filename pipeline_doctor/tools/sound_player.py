"""Sound effects for Pipeline Doctor using Windows built-in winsound.

No installation required — winsound is part of the Python standard library
on Windows. All functions are non-fatal: a missing audio device or any
other error is silently swallowed so it never interrupts the workflow.
"""

from __future__ import annotations


def play_start_sound() -> None:
    """Play a short notification sound when the pipeline run starts.

    Uses the Windows 'SystemAsterisk' alias (non-blocking).
    """
    try:
        import winsound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


def play_success_sound() -> None:
    """Play a three-note ascending melody when a fix completes successfully.

    Plays E5 → G5 → B5 as a short celebratory fanfare.
    """
    try:
        import winsound
        winsound.Beep(659, 150)   # E5
        winsound.Beep(784, 150)   # G5
        winsound.Beep(988, 300)   # B5
    except Exception:
        pass


def play_error_sound() -> None:
    """Play the Windows exclamation sound when the pipeline run fails.

    Uses the Windows 'SystemExclamation' alias (non-blocking).
    """
    try:
        import winsound
        winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


def play_thinking_sound() -> None:
    """Play a single short beep to indicate the agent is working.

    Plays a 100 ms A4 tone (440 Hz).
    """
    try:
        import winsound
        winsound.Beep(440, 100)
    except Exception:
        pass


if __name__ == "__main__":
    import time

    print("🎵 Sound Player — Smoke Test")
    print("You should hear 4 sounds:")

    print("\n1. Start sound...")
    play_start_sound()
    time.sleep(1.5)

    print("2. Thinking beep...")
    play_thinking_sound()
    time.sleep(1)

    print("3. Success melody (3 notes)...")
    play_success_sound()
    time.sleep(2)

    print("4. Error sound...")
    play_error_sound()
    time.sleep(1)

    print("\n✅ Sound test complete!")
