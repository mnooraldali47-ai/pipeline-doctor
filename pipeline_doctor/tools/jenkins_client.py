"""Jenkins REST API client using requests (no python-jenkins dependency)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth


# ── Exceptions ───────────────────────────────────────────────────────────────


class JenkinsError(Exception):
    """Base exception for all Jenkins client errors."""


class JenkinsAuthError(JenkinsError):
    """HTTP 401 or 403 — wrong credentials or insufficient permissions."""


class JenkinsNotFoundError(JenkinsError):
    """HTTP 404 — job, build, or resource does not exist."""


class JenkinsConnectionError(JenkinsError):
    """Server unreachable — not running or wrong URL."""


class JenkinsTimeoutError(JenkinsError):
    """Request exceeded the 10-second timeout."""


# ── Client ───────────────────────────────────────────────────────────────────


class JenkinsClient:
    """Thin Jenkins REST API client over HTTP Basic Auth.

    Attributes:
        url: Jenkins base URL without trailing slash.
        user: Jenkins username used for authentication.
    """

    def __init__(
        self,
        url: str | None = None,
        user: str | None = None,
        token: str | None = None,
        env_file: Path | None = None,
    ) -> None:
        """Load credentials from arguments or .env file.

        Args:
            url: Jenkins base URL. Falls back to JENKINS_URL env var.
            user: Jenkins username. Falls back to JENKINS_USER env var.
            token: Jenkins API token. Falls back to JENKINS_TOKEN env var.
            env_file: Path to .env file. Defaults to project root .env.
        """
        load_dotenv(env_file or Path(__file__).parent.parent.parent / ".env")
        self.url = (url or os.environ.get("JENKINS_URL", "")).rstrip("/")
        self.user = user or os.environ.get("JENKINS_USER", "")
        self._auth = HTTPBasicAuth(
            self.user, token or os.environ.get("JENKINS_TOKEN", "")
        )

    # ── internal ─────────────────────────────────────────────────────────────

    def _get(self, path: str) -> requests.Response:
        """Execute a GET request and raise typed exceptions on failure.

        Args:
            path: URL path starting with '/', e.g. '/api/json'.

        Returns:
            The successful requests.Response object.

        Raises:
            JenkinsAuthError: On HTTP 401 or 403.
            JenkinsNotFoundError: On HTTP 404.
            JenkinsConnectionError: When server is unreachable.
            JenkinsTimeoutError: When request exceeds 10 seconds.
            JenkinsError: On any other HTTP error status.
        """
        target = f"{self.url}{path}"
        try:
            resp = requests.get(target, auth=self._auth, timeout=10)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as exc:
            code = exc.response.status_code
            if code in (401, 403):
                raise JenkinsAuthError(
                    f"Authentication failed (HTTP {code}). "
                    "Check JENKINS_USER / JENKINS_TOKEN in .env."
                ) from exc
            if code == 404:
                raise JenkinsNotFoundError(f"Resource not found: {target}") from exc
            raise JenkinsError(f"HTTP {code} from {target}") from exc
        except requests.ConnectionError as exc:
            raise JenkinsConnectionError(
                f"Cannot reach Jenkins at {self.url}. Is the server running?"
            ) from exc
        except requests.Timeout as exc:
            raise JenkinsTimeoutError(
                f"Request timed out after 10 s: {target}"
            ) from exc

    # ── public API ────────────────────────────────────────────────────────────

    def get_info(self) -> dict[str, Any]:
        """Return Jenkins root API data plus server version.

        Returns:
            Parsed JSON dict with an extra '_jenkins_version' key taken from
            the X-Jenkins response header.
        """
        resp = self._get("/api/json")
        data: dict[str, Any] = resp.json()
        data["_jenkins_version"] = resp.headers.get("X-Jenkins", "unknown")
        return data

    def list_jobs(self) -> list[str]:
        """Return sorted names of all top-level jobs.

        Returns:
            Alphabetically sorted list of job name strings.
        """
        data = self.get_info()
        return sorted(job["name"] for job in data.get("jobs", []))

    def get_job_info(self, name: str) -> dict[str, Any]:
        """Return full API data for a specific job.

        Args:
            name: Jenkins job name (case-sensitive).

        Returns:
            Parsed JSON dict for the job.
        """
        resp = self._get(f"/job/{name}/api/json")
        return resp.json()

    def get_latest_build_number(self, job: str) -> int:
        """Return the build number of the most recent build.

        Args:
            job: Jenkins job name.

        Returns:
            Integer build number.

        Raises:
            ValueError: If the job has no builds yet.
        """
        data = self.get_job_info(job)
        last = data.get("lastBuild")
        if last is None:
            raise ValueError(f"Job '{job}' has no builds yet.")
        return int(last["number"])

    def get_build_info(self, job: str, build_nr: int) -> dict[str, Any]:
        """Return API data for a specific build.

        Args:
            job: Jenkins job name.
            build_nr: Build number.

        Returns:
            Parsed JSON dict for the build (includes 'result', 'duration', etc.).
        """
        resp = self._get(f"/job/{job}/{build_nr}/api/json")
        return resp.json()

    def get_build_log(self, job: str, build_nr: int) -> str:
        """Return the full console log for a build as plain text.

        Args:
            job: Jenkins job name.
            build_nr: Build number.

        Returns:
            Console log string.
        """
        resp = self._get(f"/job/{job}/{build_nr}/consoleText")
        return resp.text

    def is_build_failed(self, job: str, build_nr: int) -> bool:
        """Check whether a build ended with result FAILURE.

        Args:
            job: Jenkins job name.
            build_nr: Build number.

        Returns:
            True only when result == "FAILURE". All other results
            (SUCCESS, ABORTED, UNSTABLE, None/in-progress) return False.
        """
        data = self.get_build_info(job, build_nr)
        return data.get("result") == "FAILURE"
