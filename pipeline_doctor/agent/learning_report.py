"""LearningReport — generates a Markdown teaching document after each auto-fix.

After Pipeline Doctor applies a fix, this module explains the bug in
beginner-friendly terms so developers learn from every failure.

Usage:
    reporter = LearningReport()
    path = reporter.generate(diagnosis, original_code, fixed_code, job, build)
    print(f"Learning report saved: {path}")
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from .diagnosis_schema import Diagnosis
from .llm_config import get_llm
from pipeline_doctor.tools.youtube_search import search_youtube_videos

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a senior software engineer teaching a junior developer about a bug. "
    "Given a diagnosis and code fix, explain:\n\n"
    "1. Why did this bug happen? (root cause in beginner-friendly terms)\n"
    "2. What's the general concept behind it?\n"
    "3. How can it be prevented? (3-5 concrete practices)\n"
    "4. What are related concepts to learn? (2-3 topics)\n\n"
    "Be concise, educational, and encouraging.\n\n"
    "Return ONLY valid JSON with these keys:\n"
    "- explanation: string (2-3 sentences)\n"
    "- concept: string (1-2 sentences)\n"
    "- prevention: array of 3-5 short strings\n"
    "- learning_topics: array of 2-3 short strings\n"
    "- youtube_search_query: string (3-5 keywords)\n\n"
    "No markdown, no code fences, just pure JSON."
)


class LearningReport:
    """Generates Markdown learning reports from a Diagnosis + code diff.

    Each report is saved to disk and can be indexed by the Bug Museum.

    Args:
        output_dir: Directory where Markdown files are saved.
            Created automatically if it does not exist.
    """

    def __init__(self, output_dir: str = "data/bug_museum") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._llm = get_llm()

    def generate(
        self,
        diagnosis: Diagnosis,
        original_code: str,
        fixed_code: str,
        job_name: str,
        build_number: int,
        pr_url: str | None = None,
    ) -> Path:
        """Generate a Markdown learning report and save it to disk.

        Calls the LLM once to produce beginner-friendly explanations,
        then renders a structured Markdown document.

        Args:
            diagnosis: Structured diagnosis produced by DiagnosisAgent.
            original_code: Full content of the broken file before the fix.
            fixed_code: Full content of the file after the fix was applied.
            job_name: Jenkins job name, e.g. 'failing-syntax'.
            build_number: Build number the failure came from.
            pr_url: Optional URL to the pull request created by the auto-fix.

        Returns:
            Path to the saved Markdown file.
        """
        data = self._generate_explanation(diagnosis, original_code, fixed_code)

        try:
            youtube_query = data.get("youtube_search_query", diagnosis.error_type)
            videos = search_youtube_videos(youtube_query, max_results=3)
        except Exception:
            videos = []

        markdown = self._render_markdown(
            diagnosis, original_code, fixed_code,
            job_name, build_number, pr_url, data, videos,
        )
        path = self._save(job_name, build_number, diagnosis.error_type, markdown)
        logger.info("Learning report saved: %s", path)
        return path

    # ── Private helpers ───────────────────────────────────────────────────────

    def _generate_explanation(
        self,
        diagnosis: Diagnosis,
        original_code: str,
        fixed_code: str,
    ) -> dict:
        user_prompt = (
            f"Bug diagnosis:\n"
            f"- Error type: {diagnosis.error_type}\n"
            f"- Failed stage: {diagnosis.failed_stage}\n"
            f"- Root cause: {diagnosis.root_cause}\n"
            f"- Evidence: {diagnosis.root_cause_evidence}\n"
            f"- Affected file: {diagnosis.affected_file}, line {diagnosis.affected_line}\n\n"
            f"Broken code (first 500 chars):\n{original_code[:500]}\n\n"
            f"Fixed code (first 500 chars):\n{fixed_code[:500]}"
        )

        response = self._llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON explanation — using fallback")
            return {
                "explanation": f"This bug was caused by {diagnosis.root_cause}.",
                "concept": "See the diagnosis details above for more context.",
                "prevention": [
                    "Use a linter (e.g. flake8, pylint)",
                    "Write unit tests",
                    "Enable CI on every push",
                    "Do peer code reviews",
                ],
                "learning_topics": [
                    "Python syntax basics",
                    "Automated testing",
                ],
                "youtube_search_query": f"{diagnosis.error_type} python tutorial",
            }

    @staticmethod
    def _format_youtube_section(query: str, videos: list[dict]) -> str:
        """Render the YouTube section with real videos or a fallback search link."""
        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"

        if not videos:
            return (
                f"🔍 **YouTube search:** `{query}`\n\n"
                f"[Search on YouTube]({search_url})"
            )

        lines = ["**Top YouTube tutorials for this bug:**\n"]
        for i, v in enumerate(videos, 1):
            lines.append(
                f"{i}. **[{v['title']}]({v['url']})**  \n"
                f"   👤 {v['channel']} · ⏱️ {v['duration']} · 👁️ {v['view_count']} views"
            )
        lines.append(f"\n🔍 [Search more on YouTube]({search_url})")
        return "\n".join(lines)

    @staticmethod
    def _render_markdown(
        diagnosis: Diagnosis,
        original_code: str,
        fixed_code: str,
        job_name: str,
        build_number: int,
        pr_url: str | None,
        data: dict,
        videos: list[dict],
    ) -> str:
        pr_line = f"**PR:** [{pr_url}]({pr_url})" if pr_url else ""

        prevention_items = "\n".join(
            f"- {item}" for item in data.get("prevention", [])
        )
        learning_items = "\n".join(
            f"- {topic}" for topic in data.get("learning_topics", [])
        )

        code_limit = 800
        original_snippet = original_code[:code_limit] + (
            "\n... (truncated)" if len(original_code) > code_limit else ""
        )
        fixed_snippet = fixed_code[:code_limit] + (
            "\n... (truncated)" if len(fixed_code) > code_limit else ""
        )

        youtube_section = LearningReport._format_youtube_section(
            data.get("youtube_search_query", diagnosis.error_type + " python"),
            videos,
        )

        return f"""# 📚 Learning Report: {diagnosis.error_type}

**Job:** `{job_name}#{build_number}`
**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**File:** `{diagnosis.affected_file}:{diagnosis.affected_line}`
**Confidence:** {int(diagnosis.confidence * 100)}%
{pr_line}

---

## 🐛 What went wrong?

{data.get('explanation', diagnosis.root_cause)}

## 💡 The concept behind it

{data.get('concept', 'See diagnosis for details.')}

## 🔍 What was diagnosed?

**Root cause:** {diagnosis.root_cause}

**Evidence from log:**
```
{diagnosis.root_cause_evidence}
```

## 🔧 Code: Before and After

**Before (broken):**
```python
{original_snippet}
```

**After (fixed):**
```python
{fixed_snippet}
```

## 🛡️ How to prevent this in future

{prevention_items}

## 📖 What to learn next

{learning_items}

## 🎬 Learn from YouTube

{youtube_section}

---
*Generated automatically by Pipeline Doctor 🩺*
"""

    def _save(
        self,
        job_name: str,
        build_number: int,
        error_type: str,
        markdown: str,
    ) -> Path:
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_error = error_type.lower().replace(" ", "-").replace("_", "-")
        filename = f"{date_str}_{job_name}-build-{build_number}-{safe_error}.md"
        path = self.output_dir / filename
        path.write_text(markdown, encoding="utf-8")
        return path


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    print("📚 Pipeline Doctor — Learning Report Smoke Test")
    print("=" * 55)

    diagnosis = Diagnosis(
        error_type="SyntaxError",
        failed_stage="Syntax Check",
        root_cause="Missing colon at end of function definition",
        root_cause_evidence="def multiply(x, y)",
        fix_suggestion="Add colon after the parameter list",
        confidence=0.97,
        affected_file="main.py",
        affected_line=5,
    )

    original = (
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def multiply(x, y)\n"
        "    return x * y\n"
    )
    fixed = (
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def multiply(x, y):\n"
        "    return x * y\n"
    )

    try:
        reporter = LearningReport(output_dir="data/bug_museum")
        path = reporter.generate(
            diagnosis=diagnosis,
            original_code=original,
            fixed_code=fixed,
            job_name="failing-syntax",
            build_number=2,
            pr_url="https://github.com/mnooraldali47-ai/pipeline-doctor-failing-syntax/pull/3",
        )
        print(f"\n✅ Report saved: {path}")
        print(f"\n--- Preview (first 800 chars) ---")
        print(path.read_text(encoding="utf-8")[:800])
    except Exception as exc:
        print(f"\n❌ Failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
