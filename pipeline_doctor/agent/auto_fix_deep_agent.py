"""Auto-Fix DeepAgent — orchestrates the full GitHub fix workflow autonomously.

Workflow (agent-driven):
    1. Read broken file from GitHub
    2. Generate LLM fix
    3. Create new branch
    4. Commit fix to branch
    5. Open pull request

Usage:
    agent = create_auto_fix_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
"""

from __future__ import annotations

from deepagents import create_deep_agent
from langchain_core.tools import tool

from .diagnosis_schema import Diagnosis
from .fix_generator import FixGenerator
from .llm_config import get_llm
from ..tools.github_client import GitHubClient

# ── Module-level singletons shared across all tool calls ─────────────────────
_github = GitHubClient()
_fix_gen = FixGenerator()

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are Pipeline Doctor, an autonomous CI/CD fix agent. "
    "Given a diagnosis of a broken build, your job is to:\n\n"
    "1. Read the broken file from GitHub (github_read_file)\n"
    "2. Generate a code fix using the LLM (generate_code_fix)\n"
    "3. Create a new branch (create_fix_branch)\n"
    "   - Use branch name format: 'pipeline-doctor-fix-<repo-suffix>-<timestamp>'\n"
    "4. Commit the fix to that branch (commit_fix_to_branch)\n"
    "   - Use clear commit message describing what was fixed\n"
    "5. Open a pull request (open_pull_request)\n"
    "   - Include the diagnosis and confidence in the PR body\n"
    "   - Format as markdown\n\n"
    "Rules:\n"
    "- Always create a NEW branch, never commit to main\n"
    "- Always create a PR for human review\n"
    "- Use descriptive branch names and commit messages\n"
    "- Include the diagnosis in the PR body\n"
    "- Report each step you complete\n"
    "- If any step fails, explain what went wrong"
)

# ── Tools ─────────────────────────────────────────────────────────────────────


@tool
def github_read_file(repo: str, path: str, branch: str = None) -> str:
    """Read a file from a GitHub repository.

    Args:
        repo: Repository name (e.g. 'pipeline-doctor-failing-syntax').
        path: File path inside the repo (e.g. 'main.py').
        branch: Branch name. Defaults to the repo's default branch.

    Returns:
        File content as a plain string.
    """
    return _github.read_file(repo, path, branch)


@tool
def generate_code_fix(
    broken_code: str,
    error_type: str,
    root_cause: str,
    affected_file: str,
    affected_line: int,
) -> dict:
    """Generate a corrected version of a broken source file using an LLM.

    Args:
        broken_code: The complete content of the broken file.
        error_type: Short error category, e.g. 'SyntaxError'.
        root_cause: Human-readable description of the bug.
        affected_file: Filename, e.g. 'main.py'.
        affected_line: 1-based line number where the bug is located.

    Returns:
        Dict with keys 'fixed_code' (complete corrected file) and
        'explanation' (1-2 sentence description of the change).
    """
    diagnosis = Diagnosis(
        error_type=error_type,
        failed_stage="Fix",
        root_cause=root_cause,
        root_cause_evidence=root_cause,
        fix_suggestion="Fix the code",
        confidence=0.9,
        affected_file=affected_file,
        affected_line=affected_line,
    )
    fix = _fix_gen.generate_fix(broken_code, diagnosis)
    return {"fixed_code": fix.fixed_code, "explanation": fix.explanation}


@tool
def create_fix_branch(repo: str, branch_name: str) -> str:
    """Create a new branch on GitHub from the default branch.

    Args:
        repo: Repository name.
        branch_name: Name for the new branch (e.g. 'pipeline-doctor-fix-syntax-1720000000').

    Returns:
        Confirmation message including the created branch name.
    """
    _github.create_branch(repo, branch_name)
    return f"Branch created: {branch_name}"


@tool
def commit_fix_to_branch(
    repo: str,
    path: str,
    new_content: str,
    branch: str,
    message: str,
) -> str:
    """Commit corrected file content to an existing branch on GitHub.

    Args:
        repo: Repository name.
        path: File path to update (e.g. 'main.py').
        new_content: Complete corrected file content.
        branch: Target branch that must already exist.
        message: Git commit message.

    Returns:
        Confirmation string with the first 12 characters of the commit SHA.
    """
    result = _github.commit_file(repo, path, new_content, branch, message)
    sha = result.get("commit", {}).get("sha", "?")[:12]
    return f"Committed: {sha}"


@tool
def open_pull_request(
    repo: str,
    title: str,
    body: str,
    head_branch: str,
) -> str:
    """Open a GitHub pull request from a fix branch into the default branch.

    Args:
        repo: Repository name.
        title: Pull request title shown in the GitHub UI.
        body: Pull request description in Markdown.
        head_branch: Source branch that contains the fix commit.

    Returns:
        PR URL and number, e.g. 'PR created: https://github.com/.../pull/3 (#3)'.
    """
    pr = _github.create_pull_request(repo, title, body, head_branch)
    return f"PR created: {pr.get('html_url')} (#{pr.get('number')})"


# ── Agent factory ─────────────────────────────────────────────────────────────


def create_auto_fix_agent():
    """Build and return the autonomous fix DeepAgent with all tools wired up.

    Returns:
        A DeepAgent instance ready to invoke with a message dict.
    """
    return create_deep_agent(
        model=get_llm(),
        tools=[
            github_read_file,
            generate_code_fix,
            create_fix_branch,
            commit_fix_to_branch,
            open_pull_request,
        ],
        system_prompt=_SYSTEM_PROMPT,
    )


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import time

    print("🤖 Pipeline Doctor — Auto-Fix DeepAgent Demo")
    print("=" * 60)

    agent = create_auto_fix_agent()

    user_message = (
        f"There is a syntax error in the repo 'pipeline-doctor-failing-syntax'.\n"
        f"The file 'main.py' has a bug on line 5: missing colon after "
        f"'def multiply(x, y)'.\n\n"
        f"Please:\n"
        f"1. Read the file\n"
        f"2. Generate a fix\n"
        f"3. Create a new branch (use timestamp {int(time.time())} in the name)\n"
        f"4. Commit the fix to the branch\n"
        f"5. Open a pull request\n\n"
        f"Report each step."
    )

    print(f"\n📨 Task für den Agent:")
    print(user_message[:200] + "...")
    print(f"\n🚀 Agent starting ...\n")

    try:
        result = agent.invoke({
            "messages": [{"role": "user", "content": user_message}]
        })

        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            content = last.content if hasattr(last, "content") else str(last)
            print(f"\n✅ Agent Final Response:\n{content}")

        print(f"\n📊 Total steps: {len(messages)}")

    except Exception as exc:
        print(f"\n❌ Agent failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
