"""StatsTracker — persists and reports Pipeline Doctor run statistics.

All runs are appended to a JSON file so history survives restarts.
The last 100 run details are stored; aggregate counters accumulate forever.

Usage:
    tracker = StatsTracker()
    tracker.record_run(job_name="failing-syntax", build_number=2, ...)
    print(tracker.get_summary())
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_EMPTY_DATA: dict = {
    "total_runs": 0,
    "successful_fixes": 0,
    "failed_fixes": 0,
    "by_error_type": {},
    "by_mode": {},
    "total_tokens": 0,
    "total_time_seconds": 0.0,
    "confidence_sum": 0.0,
    "confidence_count": 0,
    "runs": [],
}


class StatsTracker:
    """Tracks and persists Pipeline Doctor run statistics to disk.

    Args:
        data_file: Path to the JSON file where stats are stored.
            The parent directory is created automatically if missing.
    """

    def __init__(self, data_file: str = "data/stats.json") -> None:
        self.data_file = Path(data_file)
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load existing stats from disk or return a fresh empty structure.

        Returns:
            Dict with all counter and list fields initialised.
        """
        if self.data_file.exists():
            try:
                return json.loads(self.data_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Corrupted stats file — resetting: %s", self.data_file)
        return dict(_EMPTY_DATA) | {"by_error_type": {}, "by_mode": {}, "runs": []}

    def _save(self) -> None:
        """Write current in-memory stats to disk as formatted JSON."""
        self.data_file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def record_run(
        self,
        job_name: str,
        build_number: int,
        error_type: str,
        confidence: float,
        mode: str,
        elapsed_seconds: float,
        success: bool,
        pr_url: str | None = None,
        tokens_used: int = 0,
    ) -> None:
        """Record a completed Pipeline Doctor run and persist to disk.

        Args:
            job_name: Jenkins job name, e.g. 'failing-syntax'.
            build_number: Build number that was analysed.
            error_type: Diagnosed error category, e.g. 'SyntaxError'.
            confidence: LLM confidence score in [0.0, 1.0].
            mode: CLI mode used — 'auto', 'interactive', or 'preview'.
            elapsed_seconds: Wall-clock seconds the run took.
            success: True if the workflow completed without an error.
            pr_url: URL of the created pull request, if any.
            tokens_used: Total LLM tokens consumed (0 if unknown).
        """
        self._data["total_runs"] += 1
        if success:
            self._data["successful_fixes"] += 1
        else:
            self._data["failed_fixes"] += 1

        et = error_type or "Unknown"
        self._data["by_error_type"][et] = self._data["by_error_type"].get(et, 0) + 1
        self._data["by_mode"][mode] = self._data["by_mode"].get(mode, 0) + 1

        self._data["total_tokens"] += tokens_used
        self._data["total_time_seconds"] += elapsed_seconds
        self._data["confidence_sum"] += confidence
        self._data["confidence_count"] += 1

        run_entry = {
            "timestamp": datetime.now().isoformat(),
            "job_name": job_name,
            "build_number": build_number,
            "error_type": et,
            "confidence": confidence,
            "mode": mode,
            "elapsed_seconds": round(elapsed_seconds, 1),
            "success": success,
            "pr_url": pr_url,
        }
        self._data["runs"].append(run_entry)
        self._data["runs"] = self._data["runs"][-100:]

        self._save()
        logger.debug("Run recorded: %s#%d (%s)", job_name, build_number, et)

    def get_summary(self) -> str:
        """Return a formatted multi-line text report of all statistics.

        Returns:
            Human-readable stats string, ready to print to the terminal.
        """
        d = self._data
        total = d["total_runs"]

        if total == 0:
            return "📊 No runs recorded yet."

        success_rate = (d["successful_fixes"] / total) * 100
        avg_conf = (
            d["confidence_sum"] / d["confidence_count"] * 100
            if d["confidence_count"]
            else 0.0
        )
        avg_time = d["total_time_seconds"] / total
        hours_saved = total * 15 / 60  # 15-minute manual fix estimate

        lines: list[str] = [
            "=" * 60,
            "📊 Pipeline Doctor Statistics",
            "=" * 60,
            "",
            f"  Total runs:            {total}",
            f"  ✅ Successful fixes:    {d['successful_fixes']} ({success_rate:.0f}%)",
            f"  ❌ Failed:              {d['failed_fixes']}",
            "",
            "📁 By error type:",
        ]
        for et, count in sorted(d["by_error_type"].items(), key=lambda x: -x[1]):
            lines.append(f"     {et}: {count}")

        lines += ["", "🎯 By mode:"]
        for mode, count in sorted(d["by_mode"].items(), key=lambda x: -x[1]):
            lines.append(f"     {mode}: {count}")

        lines += [
            "",
            "📈 Averages:",
            f"     Confidence:   {avg_conf:.1f}%",
            f"     Time/fix:     {avg_time:.1f}s",
        ]
        if d["total_tokens"]:
            lines.append(f"     Total tokens: {d['total_tokens']:,}")
        lines += [
            f"     ⏱️  Time saved: ~{hours_saved:.1f} hours",
            "",
            "=" * 60,
        ]

        return "\n".join(lines)


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("📊 Stats Tracker Smoke Test")
    print("=" * 40)

    tracker = StatsTracker(data_file="data/stats_test.json")

    tracker.record_run(
        job_name="failing-syntax",
        build_number=2,
        error_type="SyntaxError",
        confidence=0.95,
        mode="auto",
        elapsed_seconds=20.8,
        success=True,
        pr_url="https://github.com/example/pull/1",
    )
    tracker.record_run(
        job_name="failing-dependency",
        build_number=3,
        error_type="Dependency Resolution Failure",
        confidence=0.95,
        mode="auto",
        elapsed_seconds=13.4,
        success=True,
        pr_url="https://github.com/example/pull/2",
    )
    tracker.record_run(
        job_name="failing-tests",
        build_number=4,
        error_type="Test Failure",
        confidence=0.98,
        mode="interactive",
        elapsed_seconds=18.7,
        success=True,
    )

    print("\n" + tracker.get_summary())
    print(f"\nSaved to: {tracker.data_file}")
