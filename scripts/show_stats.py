"""Show Pipeline Doctor statistics dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline_doctor.reporting.stats_tracker import StatsTracker  # noqa: E402


def main() -> int:
    tracker = StatsTracker()
    print(tracker.get_summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
