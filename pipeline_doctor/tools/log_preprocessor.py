"""Jenkins log preprocessor — filters noise before LLM analysis.

Retains error lines with context, stage markers, and tail lines.
Removes git-checkout boilerplate and empty Pipeline-frame lines.
Reduces token cost and improves diagnosis quality.
"""

import re
from pathlib import Path
from typing import Optional


_ERROR_KEYWORDS = [
    "ERROR",
    "FAILED",
    "Exception",
    "Traceback",
    "SyntaxError",
    "AssertionError",
    "ModuleNotFoundError",
    "exit code 1",
    "exit code 127",
]

_STAGE_PATTERN = re.compile(r"\[Pipeline\] \{ \((.+?)\)")

_BOILERPLATE_PATTERNS = [
    re.compile(r"^\s*>\s*git\s"),
    re.compile(r"^\[Pipeline\] \{$"),
    re.compile(r"^\[Pipeline\] \}"),
    re.compile(r"^\[Pipeline\] //"),
    re.compile(
        r"^\[Pipeline\] (node|withEnv|stage|checkout|sh|echo|getContext)$"
    ),
    re.compile(r"^\[Pipeline\] (Start|End) of Pipeline"),
]

_CONTEXT_WINDOW = 5
_TAIL_LINES = 20


class LogPreprocessor:
    """Filters Jenkins build logs to keep diagnostically relevant lines.

    Args:
        max_lines: Hard cap on retained lines after all filtering.
    """

    def __init__(self, max_lines: int = 80) -> None:
        self.max_lines = max_lines

    def preprocess(self, raw_log: str) -> dict:
        """Filter and compress a raw Jenkins build log.

        Steps:
            1. Detect stage where first error occurred.
            2. Collect unique error keywords present in the log.
            3. Select lines: error context ± 5, last 20, stage markers.
            4. Strip boilerplate from selected lines.
            5. Trim front to max_lines if still too long.

        Args:
            raw_log: Full text of the Jenkins build log.

        Returns:
            dict with keys:
                original_size (int): Byte size of raw_log.
                compressed_size (int): Byte size of filtered_text.
                compression_ratio (float): compressed / original.
                filtered_text (str): The filtered log content.
                error_indicators (list[str]): Unique error keywords found.
                failed_stage (str | None): Stage active at first error.
        """
        lines = raw_log.splitlines()

        failed_stage = self._detect_failed_stage(lines)
        error_indicators = self._find_error_indicators(lines)
        keep_indices = self._select_lines(lines)

        filtered_lines = [lines[i] for i in sorted(keep_indices)]
        filtered_lines = [l for l in filtered_lines if not self._is_boilerplate(l)]
        filtered_lines = self._trim(filtered_lines)

        filtered_text = "\n".join(filtered_lines)
        original_bytes = len(raw_log.encode("utf-8"))
        compressed_bytes = len(filtered_text.encode("utf-8"))

        return {
            "original_size": original_bytes,
            "compressed_size": compressed_bytes,
            "compression_ratio": (
                compressed_bytes / original_bytes if original_bytes else 0.0
            ),
            "filtered_text": filtered_text,
            "error_indicators": error_indicators,
            "failed_stage": failed_stage,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_failed_stage(self, lines: list[str]) -> Optional[str]:
        """Return the stage name active when the first error keyword appears."""
        current_stage: Optional[str] = None
        for line in lines:
            match = _STAGE_PATTERN.search(line)
            if match:
                current_stage = match.group(1)
            if self._has_error(line):
                return current_stage
        return None

    @staticmethod
    def _find_error_indicators(lines: list[str]) -> list[str]:
        """Return ordered list of unique error keywords found in the log."""
        return [kw for kw in _ERROR_KEYWORDS if any(kw in line for line in lines)]

    def _select_lines(self, lines: list[str]) -> set[int]:
        """Return set of line indices to retain before boilerplate removal."""
        keep: set[int] = set()
        n = len(lines)

        # Error lines + ±5 context
        for i, line in enumerate(lines):
            if self._has_error(line):
                start = max(0, i - _CONTEXT_WINDOW)
                end = min(n, i + _CONTEXT_WINDOW + 1)
                for j in range(start, end):
                    keep.add(j)

        # Last N lines (summary / exit codes almost always here)
        for j in range(max(0, n - _TAIL_LINES), n):
            keep.add(j)

        # Stage markers (navigation context)
        for i, line in enumerate(lines):
            if _STAGE_PATTERN.search(line):
                keep.add(i)

        return keep

    def _trim(self, lines: list[str]) -> list[str]:
        """Trim from the front when filtered result exceeds max_lines."""
        if len(lines) <= self.max_lines:
            return lines
        n_removed = len(lines) - self.max_lines
        return [f"... [{n_removed} Zeilen gekürzt]"] + lines[-self.max_lines :]

    @staticmethod
    def _has_error(line: str) -> bool:
        return any(kw in line for kw in _ERROR_KEYWORDS)

    @staticmethod
    def _is_boilerplate(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        return any(p.match(stripped) for p in _BOILERPLATE_PATTERNS)


# ------------------------------------------------------------------
# Smoke test / demo
# ------------------------------------------------------------------

if __name__ == "__main__":
    log_path = (
        Path(__file__).parent.parent.parent / "logs" / "failing-tests-build-4.log"
    )

    print("🔍 Pipeline Doctor — Log Preprocessor Demo")
    print(f"   Datei: {log_path.name}\n")

    try:
        raw = log_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"❌ Datei nicht gefunden: {log_path}")
        raise SystemExit(1)

    preprocessor = LogPreprocessor(max_lines=80)
    result = preprocessor.preprocess(raw)

    ratio_pct = result["compression_ratio"] * 100
    saved_pct = 100 - ratio_pct

    print("📊 Statistik:")
    print(f"   Original  : {result['original_size']:>6} bytes")
    print(f"   Gefiltert : {result['compressed_size']:>6} bytes")
    print(f"   Kompression: {saved_pct:.0f}% eingespart ({ratio_pct:.0f}% übrig)")
    print(f"   Failed Stage: {result['failed_stage']}")
    print(f"   Error Indicators: {result['error_indicators']}")
    print()
    print("📝 Gefilterter Log:")
    print("─" * 60)
    print(result["filtered_text"])
    print("─" * 60)
    print("\n✅ Preprocessing abgeschlossen.")
