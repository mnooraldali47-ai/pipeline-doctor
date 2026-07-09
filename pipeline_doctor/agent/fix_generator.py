"""FixGenerator — reads broken code + Diagnosis, returns a FixProposal via LLM.

Usage:
    generator = FixGenerator()
    fix = generator.generate_fix(broken_code, diagnosis)
"""

from __future__ import annotations

import logging
import os

from langchain_core.messages import HumanMessage, SystemMessage

from .diagnosis_schema import Diagnosis
from .fix_schema import FixProposal
from .llm_config import get_llm

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert software engineer specialized in fixing code bugs.\n"
    "You receive broken code and a diagnosis. You return ONLY the corrected "
    "code as JSON matching the FixProposal schema.\n\n"
    "Rules:\n"
    "- Return the COMPLETE corrected file, not just the diff\n"
    "- Preserve original code style (indentation, comments, etc.)\n"
    "- Change ONLY what the diagnosis requires\n"
    "- Keep explanations BRIEF (1-2 sentences)\n"
    "- If unsure, set confidence < 0.6\n"
    "- Do NOT add commentary outside the JSON fields\n"
    "- Do NOT wrap code in markdown fences (no ``` blocks)"
)


class FixGenerator:
    """Generates corrected code for a diagnosed bug using an LLM.

    The LLM is called with a structured-output chain that forces the response
    into a FixProposal Pydantic model, eliminating the need for manual parsing.
    """

    def __init__(self) -> None:
        self._llm = get_llm()
        self._chain = self._llm.with_structured_output(FixProposal, include_raw=True)
        self._system_prompt = _SYSTEM_PROMPT

    def generate_fix(self, broken_code: str, diagnosis: Diagnosis) -> FixProposal:
        """Call the LLM and return a structured fix for the broken code.

        Args:
            broken_code: Full content of the file containing the bug.
            diagnosis: Structured diagnosis produced by DiagnosisAgent.

        Returns:
            FixProposal with the corrected file, explanation, confidence,
            and a list of changed line numbers.

        Raises:
            ValueError: If the LLM response cannot be parsed into a FixProposal.
        """
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=self._build_prompt(broken_code, diagnosis)),
        ]

        result = self._chain.invoke(messages)

        parsing_error = result.get("parsing_error")
        fix: FixProposal | None = result.get("parsed")

        if fix is None:
            raw = result.get("raw")
            raw_content = getattr(raw, "content", "") or ""
            raise ValueError(
                f"LLM output could not be parsed into FixProposal.\n"
                f"Parse error: {parsing_error}\n"
                f"Raw output (first 500 chars): {raw_content[:500]!r}"
            )

        logger.info(
            "FixProposal generated: confidence=%.2f, lines_changed=%s",
            fix.confidence,
            fix.lines_changed,
        )
        return fix

    @staticmethod
    def _build_prompt(broken_code: str, diagnosis: Diagnosis) -> str:
        numbered_lines = "\n".join(
            f"# line {i + 1}: {line}"
            for i, line in enumerate(broken_code.splitlines())
        )
        return (
            "The following code has a bug:\n\n"
            f"{numbered_lines}\n\n"
            f"Diagnosis: {diagnosis.root_cause}\n"
            f"Evidence: {diagnosis.root_cause_evidence}\n"
            f"Suggested fix: {diagnosis.fix_suggestion}\n"
            f"Affected file: {diagnosis.affected_file}, "
            f"line {diagnosis.affected_line}\n\n"
            "Task: Return the FULL corrected file content. "
            "Do not add explanations outside the JSON fields. "
            "Preserve all existing code except the fix."
        )


# ------------------------------------------------------------------
# Smoke test / demo
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.INFO, format="   %(levelname)s %(message)s")

    from pipeline_doctor.agent.diagnosis_schema import Diagnosis

    diagnosis = Diagnosis(
        error_type="SyntaxError",
        failed_stage="Syntax Check",
        root_cause="Missing colon at end of function definition",
        root_cause_evidence="def multiply(x, y)",
        fix_suggestion="Add colon after function parameters",
        confidence=0.99,
        affected_file="main.py",
        affected_line=5,
    )

    broken_code = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def multiply(x, y)\n"
        "    return x * y\n"
    )

    print("🔧 Pipeline Doctor — Fix-Generator Smoke Test")
    print(f"   Modell: {os.environ.get('GWDG_MODEL', '(aus .env)')}")
    print(f"\n📥 Kaputter Code:\n{broken_code}")
    print(f"🔍 Diagnose: {diagnosis.root_cause}")

    generator = FixGenerator()

    try:
        fix = generator.generate_fix(broken_code, diagnosis)
        print(f"\n✅ Gefixter Code:\n{fix.fixed_code}")
        print(f"\n💡 Erklärung: {fix.explanation}")
        print(f"🎯 Konfidenz: {fix.confidence}")
        print(f"📋 Geänderte Zeilen: {fix.lines_changed}")
    except Exception as exc:
        print(f"\n❌ Fehler: {exc}")
        try:
            messages = [
                SystemMessage(content=generator._system_prompt),
                HumanMessage(content=generator._build_prompt(broken_code, diagnosis)),
            ]
            result = generator._chain.invoke(messages)
            raw = result.get("raw")
            print(f"\n🔎 Raw LLM Output (erste 800 Zeichen):")
            print("-" * 60)
            print(getattr(raw, "content", "")[:800])
            print("-" * 60)
            meta = getattr(raw, "response_metadata", {}) or {}
            print(f"finish_reason: {meta.get('finish_reason', '?')}")
            print(f"tokens: {meta.get('token_usage', {})}")
        except Exception as exc2:
            print(f"Auch Debug-Call fehlgeschlagen: {exc2}")
        sys.exit(1)
