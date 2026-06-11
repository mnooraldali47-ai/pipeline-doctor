"""DiagnosisAgent — preprocesses Jenkins logs and calls the LLM for diagnosis.

Usage:
    agent = DiagnosisAgent()
    diagnosis = agent.diagnose_from_file("logs/failing-tests-build-4.log")
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .diagnosis_schema import Diagnosis
from .llm_config import get_llm
from ..tools.log_preprocessor import LogPreprocessor

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert CI/CD engineer. You analyze Jenkins build logs and "
    "return ONLY the structured Diagnosis JSON object. "
    "Rules:\n"
    "- Keep root_cause and fix_suggestion BRIEF (max 2 sentences each)\n"
    "- Keep root_cause_evidence to a single quoted line from the log\n"
    "- Do NOT explain your reasoning outside the JSON fields\n"
    "- Do NOT add commentary before or after the JSON\n"
    "- If the error is unclear, set confidence < 0.5\n"
    "- Always output valid JSON matching the Diagnosis schema"
)


class DiagnosisAgent:
    """Diagnoses Jenkins build failures using LLM-based log analysis.

    Preprocessing reduces token cost by filtering log noise before the
    LLM call. The response is parsed directly into a typed Diagnosis object.
    """

    def __init__(self) -> None:
        self._llm = get_llm()
        self._preprocessor = LogPreprocessor(max_lines=120)
        self._chain = self._llm.with_structured_output(Diagnosis, include_raw=True)

    def diagnose(self, raw_log: str) -> Diagnosis:
        """Analyse a raw Jenkins build log and return a structured diagnosis.

        Args:
            raw_log: Full text content of the Jenkins build log.

        Returns:
            Diagnosis: Structured analysis with error type, root cause,
                evidence, fix suggestion, and confidence score.

        Raises:
            ValueError: If the LLM returns output that cannot be parsed
                into a Diagnosis object.
        """
        diagnosis, _ = self.diagnose_with_stats(raw_log)
        return diagnosis

    def diagnose_with_stats(self, raw_log: str) -> tuple[Diagnosis, dict]:
        """Like diagnose() but also returns LLM call metadata.

        Args:
            raw_log: Full text content of the Jenkins build log.

        Returns:
            Tuple of (Diagnosis, stats) where stats contains:
                preprocessed (dict): Full preprocess() output.
                llm_time (float): LLM call duration in seconds.
                tokens (int): Total tokens used (0 if not reported by API).

        Raises:
            ValueError: If the LLM returns unparseable output.
        """
        preprocessed = self._preprocessor.preprocess(raw_log)
        logger.info(
            "Log preprocessed: %d → %d bytes (%.0f%% kept)",
            preprocessed["original_size"],
            preprocessed["compressed_size"],
            preprocessed["compression_ratio"] * 100,
        )

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=self._build_prompt(preprocessed)),
        ]

        t0 = time.perf_counter()
        result = self._chain.invoke(messages)
        elapsed = time.perf_counter() - t0

        self._log_usage(result.get("raw"), elapsed)

        diagnosis: Optional[Diagnosis] = result.get("parsed")
        if diagnosis is None:
            raw = result.get("raw")
            raw_content = getattr(raw, "content", "") or ""
            meta = getattr(raw, "response_metadata", {}) or {}
            finish_reason = meta.get("finish_reason", "unknown")
            if finish_reason == "length":
                max_tok = os.environ.get("GWDG_MAX_TOKENS", "600")
                truncation_hint = (
                    f" Token-Limit ({max_tok}) erreicht — LLM hat zu viel produziert. "
                    "Versuche niedrigeres max_tokens oder anderes Modell."
                )
            else:
                truncation_hint = ""
            raise ValueError(
                f"LLM output nicht parsierbar (finish_reason={finish_reason!r})."
                f"{truncation_hint}\n"
                f"Parse-Fehler: {result.get('parsing_error')}\n"
                f"Raw (erste 500 Zeichen): {raw_content[:500]!r}"
            )

        if diagnosis.failed_stage is None and preprocessed.get("failed_stage"):
            diagnosis = diagnosis.model_copy(
                update={"failed_stage": preprocessed["failed_stage"]}
            )

        raw_msg = result.get("raw")
        meta = getattr(raw_msg, "response_metadata", {}) or {}
        usage = meta.get("token_usage", {}) or {}
        tokens = int(usage.get("total_tokens", 0))

        return diagnosis, {
            "preprocessed": preprocessed,
            "llm_time": elapsed,
            "tokens": tokens,
        }

    def diagnose_from_file(self, log_path: str) -> Diagnosis:
        """Load a log file from disk and run diagnose().

        Args:
            log_path: Absolute or relative path to the Jenkins log file.

        Returns:
            Diagnosis: Structured analysis of the build failure.
        """
        return self.diagnose(Path(log_path).read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(preprocessed: dict) -> str:
        saved_pct = (1 - preprocessed["compression_ratio"]) * 100
        return (
            "Build log analysis request:\n\n"
            "Pre-analysis context (extracted by static analysis):\n"
            f"  - failed_stage    : {preprocessed['failed_stage']}\n"
            f"  - error_indicators: {preprocessed['error_indicators']}\n"
            f"  - log compressed by {saved_pct:.0f}% — only relevant lines shown\n\n"
            "Filtered build log:\n"
            "```\n"
            f"{preprocessed['filtered_text']}\n"
            "```\n\n"
            "Analyze this Jenkins build failure and provide a structured diagnosis."
        )

    @staticmethod
    def _log_usage(raw_message, elapsed: float) -> None:
        usage = {}
        if raw_message is not None:
            meta = getattr(raw_message, "response_metadata", {}) or {}
            usage = meta.get("token_usage", {})

        if usage:
            logger.info(
                "LLM call: %.2fs | tokens: %s total (%s prompt + %s completion)",
                elapsed,
                usage.get("total_tokens", "?"),
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
            )
        else:
            logger.info("LLM call: %.2fs (token usage not reported)", elapsed)


# ------------------------------------------------------------------
# Smoke test / demo
# ------------------------------------------------------------------

if __name__ == "__main__":
    import os
    from langchain_core.messages import HumanMessage, SystemMessage

    logging.basicConfig(
        level=logging.INFO,
        format="   %(levelname)s %(message)s",
    )

    log_path = (
        Path(__file__).parent.parent.parent / "logs" / "failing-tests-build-4.log"
    )

    print("🔍 Pipeline Doctor — Diagnosis Agent Demo")
    print(f"   Datei   : {log_path.name}")
    print(f"   Modell  : {os.environ.get('GWDG_MODEL', '(aus .env)')}\n")

    if not log_path.exists():
        print(f"❌ Datei nicht gefunden: {log_path}")
        raise SystemExit(1)

    try:
        agent = DiagnosisAgent()
        print("   Agent initialisiert. Preprocesse Log ...\n")

        raw_log = log_path.read_text(encoding="utf-8")
        preprocessed = agent._preprocessor.preprocess(raw_log)
        print(
            f"   Log: {preprocessed['original_size']} → {preprocessed['compressed_size']} bytes "
            f"({preprocessed['compression_ratio']*100:.0f}% übrig)"
        )
        print(f"   Failed Stage (statisch): {preprocessed['failed_stage']}")
        print(f"   Error Indicators: {preprocessed['error_indicators']}\n")

        print("   Sende an LLM ...")
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=DiagnosisAgent._build_prompt(preprocessed)),
        ]

        import time
        t0 = time.perf_counter()
        result = agent._chain.invoke(messages)
        elapsed = time.perf_counter() - t0

        # ── Debug: raw output immer zeigen ──────────────────────────────
        raw_msg = result.get("raw")
        raw_content = getattr(raw_msg, "content", "") or ""
        meta = getattr(raw_msg, "response_metadata", {}) or {}
        finish_reason = meta.get("finish_reason", "unknown")
        usage = meta.get("token_usage", {})

        print(f"\n🔎 Raw LLM-Output (erste 500 Zeichen):")
        print("─" * 50)
        print(raw_content[:500])
        print("─" * 50)
        print(f"   finish_reason : {finish_reason}")
        if usage:
            print(
                f"   Tokens        : {usage.get('total_tokens','?')} total "
                f"({usage.get('prompt_tokens','?')} prompt + "
                f"{usage.get('completion_tokens','?')} completion)"
            )
        print(f"   LLM-Zeit      : {elapsed:.2f}s")

        if finish_reason == "length":
            print(
                "\n⚠️  Token-Limit erreicht — JSON möglicherweise abgeschnitten. "
                "Setze GWDG_MODEL auf stärkeres Modell oder erhöhe max_tokens."
            )

        # ── Diagnose ausgeben ────────────────────────────────────────────
        diagnosis: Optional[Diagnosis] = result.get("parsed")
        if diagnosis is None:
            err = result.get("parsing_error")
            print(f"\n❌ Parsing fehlgeschlagen: {err}")
            raise SystemExit(1)

        # Fallback: stage aus Preprocessor falls LLM sie leer ließ
        if diagnosis.failed_stage is None and preprocessed.get("failed_stage"):
            diagnosis = diagnosis.model_copy(
                update={"failed_stage": preprocessed["failed_stage"]}
            )

        print()
        print("🔍 Diagnose")
        print("─" * 50)
        print(f"   Error Type    : {diagnosis.error_type}")
        print(f"   Failed Stage  : {diagnosis.failed_stage}")
        print(f"   Root Cause    : {diagnosis.root_cause}")
        print(f"   Evidence      : {diagnosis.root_cause_evidence}")
        print(f"   Fix           : {diagnosis.fix_suggestion}")
        print(f"   Confidence    : {diagnosis.confidence:.2f}")
        print(f"   File          : {diagnosis.affected_file}")
        print(f"   Line          : {diagnosis.affected_line}")
        print("─" * 50)
        print("\n✅ Diagnose abgeschlossen.")

    except SystemExit:
        raise
    except ValueError as e:
        print(f"\n❌ Konfigurationsfehler: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        raise SystemExit(1)
