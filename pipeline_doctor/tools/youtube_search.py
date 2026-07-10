"""YouTube video search via yt-dlp — no API key required.

Used by LearningReport to embed real tutorial links in bug reports.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def search_youtube_videos(query: str, max_results: int = 3) -> list[dict]:
    """Search YouTube for tutorial videos matching a query.

    Uses yt-dlp in metadata-only mode — no video is downloaded.
    Returns an empty list on any error so callers never crash.

    Args:
        query: Search terms, e.g. 'python syntax error tutorial'.
        max_results: Maximum number of videos to return. Defaults to 3.

    Returns:
        List of dicts, each with keys:
            title (str): Video title.
            url (str): Direct link to the video.
            channel (str): Uploader / channel name.
            duration (str): Formatted duration, e.g. '10:23' or '1:15:33'.
            view_count (str): Formatted view count, e.g. '2.3M', '450K'.
    """
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        logger.warning("yt-dlp not installed — run: pip install yt-dlp")
        return []

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            search_query = f"ytsearch{max_results}:{query}"
            result = ydl.extract_info(search_query, download=False)
            entries = result.get("entries", []) if result else []

            videos: list[dict] = []
            for entry in entries[:max_results]:
                if not entry:
                    continue

                views_str = _format_views(entry.get("view_count"))
                duration_str = _format_duration(entry.get("duration"))
                video_id = entry.get("id", "")
                url = entry.get("url") or (
                    f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
                )

                videos.append({
                    "title": entry.get("title", "Untitled"),
                    "url": url,
                    "channel": entry.get("uploader", "Unknown"),
                    "duration": duration_str,
                    "view_count": views_str,
                })

            return videos

    except Exception as exc:
        logger.warning("YouTube search failed (returning empty list): %s", exc)
        return []


def _format_views(views: int | None) -> str:
    """Format a raw view count integer into a human-readable string."""
    if views is None:
        return "?"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K"
    return str(views)


def _format_duration(seconds: int | float | None) -> str:
    """Format a duration in seconds into HH:MM:SS or MM:SS."""
    if seconds is None:
        return "?"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


if __name__ == "__main__":
    print("🎬 YouTube Search Smoke Test")
    print("=" * 45)

    videos = search_youtube_videos("python syntax error tutorial", max_results=3)

    if not videos:
        print("⚠️  No videos found (yt-dlp may be blocked or not installed)")
    else:
        for i, v in enumerate(videos, 1):
            print(f"\n{i}. {v['title']}")
            print(f"   👤 {v['channel']}  |  ⏱️  {v['duration']}  |  👁️  {v['view_count']} views")
            print(f"   🔗 {v['url']}")
