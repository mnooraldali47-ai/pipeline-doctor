"""GitHub REST API v3 client — pure requests, no PyGithub."""

from __future__ import annotations

import base64
import os
import sys

import requests
from dotenv import find_dotenv, load_dotenv


class GitHubClient:
    """Thin wrapper around the GitHub REST API v3.

    Attributes:
        user: GitHub username loaded from GITHUB_USER env var.
        token: Personal access token loaded from GITHUB_TOKEN env var.
        base_url: GitHub API base URL.
    """

    def __init__(self) -> None:
        """Load credentials from .env and validate token format.

        Raises:
            ValueError: If GITHUB_TOKEN does not start with 'ghp_'.
        """
        load_dotenv(find_dotenv())
        self.user: str = os.environ["GITHUB_USER"]
        self.token: str = os.environ["GITHUB_TOKEN"]
        self.base_url: str = "https://api.github.com"

        if not self.token.startswith("ghp_"):
            raise ValueError(
                f"GITHUB_TOKEN has unexpected format (must start with 'ghp_'): "
                f"{self.token[:8]}..."
            )

    def _headers(self) -> dict[str, str]:
        """Return standard GitHub API auth headers.

        Returns:
            Dict with Authorization, Accept, and X-GitHub-Api-Version headers.
        """
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_repo_info(self, repo: str) -> dict[str, str | bool]:
        """Fetch basic metadata for a repository.

        Args:
            repo: Repository name (without owner prefix).

        Returns:
            Dict with keys: name, default_branch, private, html_url.

        Raises:
            ValueError: If the repository is not found (HTTP 404).
        """
        url = f"{self.base_url}/repos/{self.user}/{repo}"
        response = requests.get(url, headers=self._headers(), timeout=10)

        if response.status_code == 404:
            raise ValueError(f"Repo not found: {repo}")

        response.raise_for_status()
        data = response.json()

        return {
            "name": data["name"],
            "default_branch": data["default_branch"],
            "private": data["private"],
            "html_url": data["html_url"],
        }

    def read_file(self, repo: str, path: str, branch: str | None = None) -> str:
        """Read a file from a GitHub repository and return its decoded content.

        Args:
            repo: Repository name (without owner prefix).
            path: Path to the file within the repository.
            branch: Branch or ref to read from. Defaults to the repo's default branch.

        Returns:
            UTF-8 decoded file content as a string.

        Raises:
            FileNotFoundError: If the file does not exist at the given path (HTTP 404).
        """
        if branch is None:
            branch = self.get_repo_info(repo)["default_branch"]

        url = f"{self.base_url}/repos/{self.user}/{repo}/contents/{path}"
        response = requests.get(
            url,
            headers=self._headers(),
            params={"ref": branch},
            timeout=10,
        )

        if response.status_code == 404:
            raise FileNotFoundError(f"File not found: {repo}/{path}")

        response.raise_for_status()
        data = response.json()

        raw = base64.b64decode(data["content"])
        return raw.decode("utf-8")

    def list_repos(self) -> list[dict[str, str | None]]:
        """List all public repositories for the configured user.

        Returns:
            List of dicts with keys: name, description, default_branch.
        """
        url = f"{self.base_url}/users/{self.user}/repos"
        response = requests.get(
            url,
            headers=self._headers(),
            params={"per_page": 100},
            timeout=10,
        )
        response.raise_for_status()

        return [
            {
                "name": r["name"],
                "description": r.get("description"),
                "default_branch": r["default_branch"],
            }
            for r in response.json()
        ]

    def get_branch_sha(self, repo: str, branch: str) -> str:
        """Return the HEAD commit SHA for a branch.

        Args:
            repo: Repository name (without owner prefix).
            branch: Branch name, e.g. 'main'.

        Returns:
            The full SHA string of the branch HEAD commit.

        Raises:
            ValueError: If the branch does not exist (HTTP 404).
        """
        url = f"{self.base_url}/repos/{self.user}/{repo}/git/refs/heads/{branch}"
        response = requests.get(url, headers=self._headers(), timeout=10)

        if response.status_code == 404:
            raise ValueError(f"Branch not found: {repo}#{branch}")

        response.raise_for_status()
        return response.json()["object"]["sha"]

    def create_branch(
        self,
        repo: str,
        new_branch: str,
        base_branch: str | None = None,
    ) -> dict:
        """Create a new branch from an existing branch's HEAD.

        Args:
            repo: Repository name (without owner prefix).
            new_branch: Name for the new branch to create.
            base_branch: Branch to branch off from. Defaults to the repo's
                default branch when None.

        Returns:
            The raw GitHub API response dict for the newly created ref.

        Raises:
            ValueError: If base_branch does not exist, or if new_branch
                already exists (HTTP 422).
        """
        if base_branch is None:
            base_branch = self.get_repo_info(repo)["default_branch"]

        sha = self.get_branch_sha(repo, base_branch)

        url = f"{self.base_url}/repos/{self.user}/{repo}/git/refs"
        body = {"ref": f"refs/heads/{new_branch}", "sha": sha}
        response = requests.post(url, headers=self._headers(), json=body, timeout=10)

        if response.status_code == 422:
            raise ValueError(f"Branch already exists: {new_branch}")

        response.raise_for_status()
        return response.json()

    def delete_branch(self, repo: str, branch: str) -> None:
        """Delete a branch from a repository.

        Args:
            repo: Repository name (without owner prefix).
            branch: Branch name to delete.

        Returns:
            None on success (HTTP 204).

        Raises:
            ValueError: If the branch does not exist (HTTP 404).
        """
        url = f"{self.base_url}/repos/{self.user}/{repo}/git/refs/heads/{branch}"
        response = requests.delete(url, headers=self._headers(), timeout=10)

        if response.status_code == 404:
            raise ValueError(f"Branch not found: {branch}")

        response.raise_for_status()

    def get_file_sha(
        self,
        repo: str,
        path: str,
        branch: str | None = None,
    ) -> str:
        """Return the blob SHA of a file as recorded by the GitHub contents API.

        This SHA is required by the GitHub PUT /contents endpoint to detect
        conflicts when updating an existing file.

        Args:
            repo: Repository name (without owner prefix).
            path: Path to the file within the repository.
            branch: Branch or ref to read from. Defaults to the repo's
                default branch when None.

        Returns:
            The blob SHA string for the file at the given path and branch.

        Raises:
            FileNotFoundError: If the file does not exist (HTTP 404).
        """
        if branch is None:
            branch = self.get_repo_info(repo)["default_branch"]

        url = f"{self.base_url}/repos/{self.user}/{repo}/contents/{path}"
        response = requests.get(
            url,
            headers=self._headers(),
            params={"ref": branch},
            timeout=10,
        )

        if response.status_code == 404:
            raise FileNotFoundError(f"File not found: {repo}/{path}")

        response.raise_for_status()
        return response.json()["sha"]

    def commit_file(
        self,
        repo: str,
        path: str,
        new_content: str,
        branch: str,
        commit_message: str,
    ) -> dict:
        """Write new content to a file and create a commit on the given branch.

        Args:
            repo: Repository name (without owner prefix).
            path: Path to the file to update within the repository.
            new_content: Full new content of the file as a plain string.
            branch: Branch to commit to (must already exist).
            commit_message: Git commit message.

        Returns:
            The raw GitHub API response dict, which includes 'commit' (with
            'sha') and 'content' (with the new blob metadata).

        Raises:
            ValueError: If the branch or file is not found (HTTP 404), or if
                the file SHA is stale and a conflict is detected (HTTP 409).
        """
        file_sha = self.get_file_sha(repo, path, branch)

        encoded = base64.b64encode(new_content.encode("utf-8")).decode("ascii")

        url = f"{self.base_url}/repos/{self.user}/{repo}/contents/{path}"
        body = {
            "message": commit_message,
            "content": encoded,
            "branch": branch,
            "sha": file_sha,
        }
        response = requests.put(url, headers=self._headers(), json=body, timeout=10)

        if response.status_code == 404:
            raise ValueError(f"Branch or file not found: {branch}#{path}")

        if response.status_code == 409:
            raise ValueError(f"Conflict on {path}: SHA outdated")

        response.raise_for_status()
        return response.json()

    def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str | None = None,
        draft: bool = False,
    ) -> dict:
        """Open a pull request on GitHub.

        Args:
            repo: Repository name (without owner prefix).
            title: PR title shown in the GitHub UI.
            body: PR description in Markdown.
            head: Source branch name (the branch containing the fix).
            base: Target branch to merge into. Defaults to the repo's default
                branch when None.
            draft: If True, the PR is created as a draft. Defaults to False.

        Returns:
            The raw GitHub API response dict, which includes 'html_url',
            'number', 'id', 'state', and more.

        Raises:
            ValueError: If GitHub rejects the request due to validation errors
                (HTTP 422) or if the repo or branch is not found (HTTP 404).
        """
        if base is None:
            base = self.get_repo_info(repo)["default_branch"]

        url = f"{self.base_url}/repos/{self.user}/{repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }
        response = requests.post(
            url, headers=self._headers(), json=payload, timeout=10
        )

        if response.status_code == 422:
            message = response.json().get("message", "unknown")
            raise ValueError(f"PR creation failed: {message}")

        if response.status_code == 404:
            raise ValueError(f"Repo or branch not found: {repo}#{head}→{base}")

        response.raise_for_status()
        return response.json()

    def close_pull_request(self, repo: str, pr_number: int) -> dict:
        """Close an open pull request without merging.

        Args:
            repo: Repository name (without owner prefix).
            pr_number: GitHub PR number (integer shown after '#' in the UI).

        Returns:
            The raw GitHub API response dict for the updated pull request.
        """
        url = f"{self.base_url}/repos/{self.user}/{repo}/pulls/{pr_number}"
        response = requests.patch(
            url, headers=self._headers(), json={"state": "closed"}, timeout=10
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    print("🐙 Pipeline Doctor — GitHub-Client Smoke Test")
    print("=" * 50)

    try:
        client = GitHubClient()
        print(f"✅ Authenticated as: {client.user}")
    except (KeyError, ValueError) as exc:
        print(f"❌ Init failed: {exc}")
        sys.exit(1)

    print("\n📋 Listing repos...")
    try:
        repos = client.list_repos()
        for r in repos:
            print(f"  • {r['name']}")
        print(f"✅ {len(repos)} repo(s) found")
    except requests.HTTPError as exc:
        print(f"❌ list_repos failed: {exc}")
        sys.exit(1)

    target_repo = "pipeline-doctor-failing-syntax"
    target_file = "main.py"

    print(f"\n📖 Reading {target_file} from {target_repo}...")
    try:
        content = client.read_file(target_repo, target_file)
        print(f"✅ File length: {len(content)} characters")
        print("\n--- First 500 characters ---")
        print(content[:500])
    except FileNotFoundError as exc:
        print(f"❌ File not found: {exc}")
        sys.exit(1)
    except (ValueError, requests.HTTPError) as exc:
        print(f"❌ read_file failed: {exc}")
        sys.exit(1)

    import time

    print("\n🌿 Testing branch creation ...")
    test_branch = f"pipeline-doctor-test-branch-{int(time.time())}"

    try:
        result = client.create_branch(
            repo="pipeline-doctor-failing-syntax",
            new_branch=test_branch,
        )
        print(f"✅ Branch created: {test_branch}")
        print(f"   Ref: {result.get('ref', '?')}")
        print(f"   SHA: {result.get('object', {}).get('sha', '?')[:12]}")

        print(f"\n🗑️  Cleanup: deleting test branch ...")
        client.delete_branch(
            repo="pipeline-doctor-failing-syntax",
            branch=test_branch,
        )
        print(f"✅ Branch deleted: {test_branch}")
    except Exception as exc:
        print(f"❌ Branch test failed: {exc}")

    print("\n💾 Testing commit workflow (erstellt Branch + Commit + löscht Branch) ...")
    fix_branch = f"pipeline-doctor-test-fix-{int(time.time())}"

    try:
        # 1. Branch erstellen
        print(f"   1. Erstelle Test-Branch: {fix_branch}")
        client.create_branch(
            repo="pipeline-doctor-failing-syntax",
            new_branch=fix_branch,
        )
        print(f"   ✅ Branch erstellt")

        # 2. Datei lesen
        print(f"   2. Lese main.py aus dem Branch")
        original = client.read_file(
            repo="pipeline-doctor-failing-syntax",
            path="main.py",
            branch=fix_branch,
        )
        print(f"   ✅ Original ({len(original)} Zeichen)")

        # 3. Fix generieren (simuliert)
        fixed = original.replace("def multiply(x, y)", "def multiply(x, y):")
        print(f"   3. Fix generiert (Doppelpunkt eingefügt)")

        # 4. Committen
        print(f"   4. Committe Fix in Branch")
        result = client.commit_file(
            repo="pipeline-doctor-failing-syntax",
            path="main.py",
            new_content=fixed,
            branch=fix_branch,
            commit_message="test: add missing colon (Pipeline Doctor smoke test)",
        )
        commit_sha = result.get("commit", {}).get("sha", "?")[:12]
        print(f"   ✅ Commit erstellt: {commit_sha}")

        # 5. Verifikation
        print(f"   5. Verifiziere Fix im Branch")
        fixed_after = client.read_file(
            repo="pipeline-doctor-failing-syntax",
            path="main.py",
            branch=fix_branch,
        )
        if "def multiply(x, y):" in fixed_after:
            print(f"   ✅ Fix bestätigt: Doppelpunkt ist da!")
        else:
            print(f"   ❌ Fix NICHT bestätigt!")

        # 6. Cleanup
        print(f"   6. Cleanup: lösche Test-Branch")
        client.delete_branch(
            repo="pipeline-doctor-failing-syntax",
            branch=fix_branch,
        )
        print(f"   ✅ Branch gelöscht")

        print(f"\n✅ Kompletter Commit-Workflow erfolgreich!")

    except Exception as exc:
        print(f"\n❌ Workflow fehlgeschlagen: {exc}")
        try:
            client.delete_branch(
                repo="pipeline-doctor-failing-syntax",
                branch=fix_branch,
            )
            print(f"   Cleanup: Test-Branch gelöscht.")
        except Exception:
            print(f"   ⚠️  Test-Branch {fix_branch} könnte noch existieren.")

    print("\n🔄 Testing Pull-Request-Erstellung (End-to-End) ...")
    pr_branch = f"pipeline-doctor-test-pr-{int(time.time())}"
    pr_number = None

    try:
        # 1. Branch erstellen
        print(f"   1. Erstelle Branch: {pr_branch}")
        client.create_branch(
            repo="pipeline-doctor-failing-syntax",
            new_branch=pr_branch,
        )
        print(f"   ✅ Branch erstellt")

        # 2. Fix committen
        print(f"   2. Committe simulierten Fix in Branch")
        original = client.read_file(
            repo="pipeline-doctor-failing-syntax",
            path="main.py",
            branch=pr_branch,
        )
        fixed = original.replace("def multiply(x, y)", "def multiply(x, y):")
        client.commit_file(
            repo="pipeline-doctor-failing-syntax",
            path="main.py",
            new_content=fixed,
            branch=pr_branch,
            commit_message="fix: add missing colon in multiply function",
        )
        print(f"   ✅ Fix committet")

        # 3. Pull Request erstellen
        print(f"   3. Erstelle Pull Request")
        pr_body = (
            "## Automatische Diagnose\n\n"
            "**Fehlertyp:** SyntaxError\n"
            "**Datei:** main.py, Zeile 5\n"
            "**Ursache:** Fehlender Doppelpunkt am Ende der Funktionsdefinition\n\n"
            "## Fix\n\n"
            "Doppelpunkt nach `def multiply(x, y)` hinzugefügt.\n\n"
            "## Konfidenz\n\n"
            "0.95 (sehr hoch)\n\n"
            "---\n\n"
            "*Automatisch erstellt von Pipeline Doctor (Smoke Test)*"
        )
        pr = client.create_pull_request(
            repo="pipeline-doctor-failing-syntax",
            title="🤖 Auto-fix: Missing colon in main.py (Smoke Test)",
            body=pr_body,
            head=pr_branch,
        )
        pr_number = pr.get("number")
        pr_url = pr.get("html_url")
        print(f"   ✅ Pull Request erstellt: #{pr_number}")
        print(f"      URL: {pr_url}")

        # 4. Cleanup: PR schließen + Branch löschen
        print(f"\n   🗑️  Cleanup: schließe PR + lösche Branch")
        client.close_pull_request(
            repo="pipeline-doctor-failing-syntax",
            pr_number=pr_number,
        )
        print(f"   ✅ PR #{pr_number} geschlossen")
        client.delete_branch(
            repo="pipeline-doctor-failing-syntax",
            branch=pr_branch,
        )
        print(f"   ✅ Branch gelöscht")

        print(f"\n🎉 Kompletter Auto-Fix-Workflow erfolgreich!")
        print(f"   Branch → Commit → PR → Close → Delete")

    except Exception as exc:
        print(f"\n❌ Workflow fehlgeschlagen: {exc}")
        try:
            if pr_number:
                client.close_pull_request(
                    repo="pipeline-doctor-failing-syntax",
                    pr_number=pr_number,
                )
        except Exception:
            pass
        try:
            client.delete_branch(
                repo="pipeline-doctor-failing-syntax",
                branch=pr_branch,
            )
        except Exception:
            pass
