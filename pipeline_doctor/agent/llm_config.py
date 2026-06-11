"""LLM configuration layer for Pipeline Doctor.

Provides a pre-configured ChatOpenAI instance pointing at the GWDG/KISSKI
endpoint. All other agent modules import get_llm() from here.
"""

import os
from dotenv import find_dotenv, load_dotenv
from langchain_openai import ChatOpenAI


def get_llm() -> ChatOpenAI:
    """Return a configured ChatOpenAI instance using the GWDG/KISSKI endpoint.

    Loads .env from the project root (walks up from this file until found).
    Reads GWDG_API_KEY, GWDG_API_BASE_URL, and GWDG_MODEL from the environment.

    Returns:
        ChatOpenAI: Ready-to-use LLM instance with temperature=0.3 and
            max_tokens=1000, suitable for structured code-analysis tasks.

    Raises:
        ValueError: If GWDG_API_KEY or GWDG_API_BASE_URL are not set.
    """
    load_dotenv(find_dotenv())

    api_key = os.environ.get("GWDG_API_KEY")
    api_base = os.environ.get("GWDG_API_BASE_URL")
    model = os.environ.get("GWDG_MODEL", "meta-llama-3.1-8b-instruct")

    if not api_key:
        raise ValueError("GWDG_API_KEY not set — check your .env file.")
    if not api_base:
        raise ValueError("GWDG_API_BASE_URL not set — check your .env file.")

    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=api_base,
        temperature=0.3,
        max_tokens=600,
    )


if __name__ == "__main__":
    from langchain_core.messages import HumanMessage, SystemMessage

    print("🤖 Pipeline Doctor — LLM Smoke Test")
    print(f"   Lade Konfiguration aus .env ...")

    try:
        llm = get_llm()
        model_name = os.environ.get("GWDG_MODEL", "meta-llama-3.1-8b-instruct")
        base_url = os.environ.get("GWDG_API_BASE_URL", "")
        print(f"   Modell : {model_name}")
        print(f"   Endpunkt: {base_url}")
        print()

        messages = [
            SystemMessage(content="You are a CI/CD expert. Be concise."),
            HumanMessage(
                content="What does 'ModuleNotFoundError' mean in 1 sentence?"
            ),
        ]

        print("   Sende Testanfrage ...")
        response = llm.invoke(messages)
        print(f"\n✅ Antwort:\n   {response.content}\n")

    except ValueError as e:
        print(f"\n❌ Konfigurationsfehler: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n❌ LLM-Fehler: {e}")
        raise SystemExit(1)
