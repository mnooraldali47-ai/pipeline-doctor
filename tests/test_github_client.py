"""Unit tests for GitHubClient — all HTTP calls are mocked."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline_doctor.tools.github_client import GitHubClient

# ── Fixtures & helpers ────────────────────────────────────────────────────────

VALID_ENV = {
    "GITHUB_USER": "test-user",
    "GITHUB_TOKEN": "ghp_faketoken1234567890",
}


def _make_response(status: int, body: object) -> MagicMock:
    """Build a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = body
    if status >= 400:
        from requests.exceptions import HTTPError

        mock.raise_for_status.side_effect = HTTPError(response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


# ── Init tests ────────────────────────────────────────────────────────────────


def test_init_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHubClient initialises without error when token starts with 'ghp_'."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    assert client.user == "test-user"
    assert client.token == "ghp_faketoken1234567890"


def test_init_invalid_token_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHubClient raises ValueError when token does not start with 'ghp_'."""
    monkeypatch.setenv("GITHUB_USER", "test-user")
    monkeypatch.setenv("GITHUB_TOKEN", "invalid_token_no_prefix")

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            with pytest.raises(ValueError, match="ghp_"):
                GitHubClient()


# ── get_repo_info tests ───────────────────────────────────────────────────────


def test_get_repo_info_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_repo_info returns the expected subset of fields."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    api_body = {
        "name": "my-repo",
        "default_branch": "main",
        "private": False,
        "html_url": "https://github.com/test-user/my-repo",
        "extra_field": "ignored",
    }

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    with patch("requests.get", return_value=_make_response(200, api_body)):
        info = client.get_repo_info("my-repo")

    assert info == {
        "name": "my-repo",
        "default_branch": "main",
        "private": False,
        "html_url": "https://github.com/test-user/my-repo",
    }


def test_get_repo_info_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_repo_info raises ValueError on HTTP 404."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    with patch("requests.get", return_value=_make_response(404, {})):
        with pytest.raises(ValueError, match="missing-repo"):
            client.get_repo_info("missing-repo")


# ── read_file tests ───────────────────────────────────────────────────────────


def test_read_file_decodes_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    """read_file correctly decodes base64-encoded content from GitHub API."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    file_text = "def hello():\n    print('hello world')\n"
    repo_info_body = {
        "name": "my-repo",
        "default_branch": "main",
        "private": False,
        "html_url": "https://github.com/test-user/my-repo",
    }
    file_body = {"content": _b64(file_text), "encoding": "base64"}

    responses = [
        _make_response(200, repo_info_body),  # get_repo_info call
        _make_response(200, file_body),        # contents call
    ]

    with patch("requests.get", side_effect=responses):
        result = client.read_file("my-repo", "main.py")

    assert result == file_text


def test_read_file_explicit_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """read_file skips get_repo_info when branch is explicitly provided."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    file_text = "x = 1\n"
    file_body = {"content": _b64(file_text), "encoding": "base64"}

    with patch("requests.get", return_value=_make_response(200, file_body)) as mock_get:
        result = client.read_file("my-repo", "app.py", branch="feature-x")

    assert result == file_text
    # Only one HTTP call — no get_repo_info lookup needed
    assert mock_get.call_count == 1


def test_read_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """read_file raises FileNotFoundError on HTTP 404."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    with patch("requests.get", return_value=_make_response(404, {})):
        with pytest.raises(FileNotFoundError, match="my-repo/missing.py"):
            client.read_file("my-repo", "missing.py", branch="main")


# ── list_repos tests ──────────────────────────────────────────────────────────


def test_list_repos_returns_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """list_repos returns correctly shaped list of repo dicts."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    api_body = [
        {"name": "repo-a", "description": "First repo", "default_branch": "main"},
        {"name": "repo-b", "description": None, "default_branch": "master"},
    ]

    with patch("requests.get", return_value=_make_response(200, api_body)):
        repos = client.list_repos()

    assert len(repos) == 2
    assert repos[0] == {"name": "repo-a", "description": "First repo", "default_branch": "main"}
    assert repos[1] == {"name": "repo-b", "description": None, "default_branch": "master"}


# ── get_branch_sha tests ──────────────────────────────────────────────────────


def test_get_branch_sha_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_branch_sha returns the SHA string from the GitHub refs endpoint."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    api_body = {"ref": "refs/heads/main", "object": {"sha": "abc123def456"}}

    with patch("requests.get", return_value=_make_response(200, api_body)):
        sha = client.get_branch_sha("my-repo", "main")

    assert sha == "abc123def456"


def test_get_branch_sha_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_branch_sha raises ValueError on HTTP 404."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    with patch("requests.get", return_value=_make_response(404, {})):
        with pytest.raises(ValueError, match="my-repo#ghost-branch"):
            client.get_branch_sha("my-repo", "ghost-branch")


# ── create_branch tests ───────────────────────────────────────────────────────


def test_create_branch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_branch POSTs correct ref name when base_branch is explicit."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    sha_body = {"ref": "refs/heads/main", "object": {"sha": "deadbeef1234"}}
    created_body = {"ref": "refs/heads/fix/my-fix", "object": {"sha": "deadbeef1234"}}

    with patch("requests.get", return_value=_make_response(200, sha_body)):
        with patch("requests.post", return_value=_make_response(201, created_body)) as mock_post:
            result = client.create_branch("my-repo", "fix/my-fix", base_branch="main")

    assert result["ref"] == "refs/heads/fix/my-fix"
    call_kwargs = mock_post.call_args
    posted_body = call_kwargs.kwargs.get("json") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else call_kwargs.kwargs.get("json")
    assert "refs/heads/fix/my-fix" in str(mock_post.call_args)


def test_create_branch_uses_default_when_no_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_branch calls get_repo_info to resolve default_branch when base_branch is None."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    repo_info_body = {
        "name": "my-repo",
        "default_branch": "main",
        "private": False,
        "html_url": "https://github.com/test-user/my-repo",
    }
    sha_body = {"ref": "refs/heads/main", "object": {"sha": "cafebabe5678"}}
    created_body = {"ref": "refs/heads/feature-x", "object": {"sha": "cafebabe5678"}}

    get_responses = [
        _make_response(200, repo_info_body),  # get_repo_info
        _make_response(200, sha_body),         # get_branch_sha
    ]

    with patch("requests.get", side_effect=get_responses) as mock_get:
        with patch("requests.post", return_value=_make_response(201, created_body)):
            result = client.create_branch("my-repo", "feature-x")

    # Two GET calls: repo_info + branch sha
    assert mock_get.call_count == 2
    assert result["ref"] == "refs/heads/feature-x"


def test_create_branch_already_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_branch raises ValueError on HTTP 422 (ref already exists)."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    sha_body = {"ref": "refs/heads/main", "object": {"sha": "aabbccdd1234"}}

    with patch("requests.get", return_value=_make_response(200, sha_body)):
        with patch("requests.post", return_value=_make_response(422, {"message": "Reference already exists"})):
            with pytest.raises(ValueError, match="already exists"):
                client.create_branch("my-repo", "existing-branch", base_branch="main")


# ── delete_branch tests ───────────────────────────────────────────────────────


def test_delete_branch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """delete_branch returns None on HTTP 204."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_resp.raise_for_status.return_value = None

    with patch("requests.delete", return_value=mock_resp):
        result = client.delete_branch("my-repo", "old-branch")

    assert result is None


def test_delete_branch_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """delete_branch raises ValueError on HTTP 404."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("requests.delete", return_value=mock_resp):
        with pytest.raises(ValueError, match="ghost-branch"):
            client.delete_branch("my-repo", "ghost-branch")


# ── get_file_sha tests ────────────────────────────────────────────────────────


def test_get_file_sha_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_file_sha returns the blob SHA from the contents endpoint."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    api_body = {
        "name": "main.py",
        "sha": "blobsha9876",
        "content": _b64("x = 1\n"),
        "encoding": "base64",
    }

    with patch("requests.get", return_value=_make_response(200, api_body)):
        sha = client.get_file_sha("my-repo", "main.py", branch="main")

    assert sha == "blobsha9876"


def test_get_file_sha_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_file_sha raises FileNotFoundError on HTTP 404."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    with patch("requests.get", return_value=_make_response(404, {})):
        with pytest.raises(FileNotFoundError, match="my-repo/missing.py"):
            client.get_file_sha("my-repo", "missing.py", branch="main")


# ── commit_file tests ─────────────────────────────────────────────────────────


def _make_put_response(status: int, body: object) -> MagicMock:
    """Build a mock requests.Response for PUT calls."""
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = body
    if status >= 400:
        from requests.exceptions import HTTPError
        mock.raise_for_status.side_effect = HTTPError(response=mock)
    else:
        mock.raise_for_status.return_value = None
    return mock


def test_commit_file_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """commit_file PUTs base64-encoded content with correct SHA, branch, message."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    file_content = "def add(a, b):\n    return a + b\n"
    old_blob_sha = "oldblobsha001"
    expected_b64 = base64.b64encode(file_content.encode("utf-8")).decode("ascii")

    get_body = {"name": "main.py", "sha": old_blob_sha, "content": _b64(file_content)}
    put_body = {
        "commit": {"sha": "newcommitsha999", "message": "fix: add colon"},
        "content": {"sha": "newblobsha002"},
    }

    with patch("requests.get", return_value=_make_response(200, get_body)):
        with patch("requests.put", return_value=_make_put_response(200, put_body)) as mock_put:
            result = client.commit_file(
                repo="my-repo",
                path="main.py",
                new_content=file_content,
                branch="fix-branch",
                commit_message="fix: add colon",
            )

    assert result["commit"]["sha"] == "newcommitsha999"

    put_body_sent = mock_put.call_args.kwargs["json"]
    assert put_body_sent["content"] == expected_b64
    assert put_body_sent["sha"] == old_blob_sha
    assert put_body_sent["branch"] == "fix-branch"
    assert put_body_sent["message"] == "fix: add colon"


def test_commit_file_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """commit_file raises ValueError on HTTP 409 (stale SHA conflict)."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    get_body = {"name": "main.py", "sha": "stalesha", "content": _b64("x=1")}

    with patch("requests.get", return_value=_make_response(200, get_body)):
        with patch("requests.put", return_value=_make_put_response(409, {"message": "Conflict"})):
            with pytest.raises(ValueError, match="Conflict"):
                client.commit_file(
                    repo="my-repo",
                    path="main.py",
                    new_content="x = 2\n",
                    branch="fix-branch",
                    commit_message="fix: update x",
                )


def test_commit_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """commit_file raises ValueError on HTTP 404 from the PUT endpoint."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    get_body = {"name": "main.py", "sha": "somesha", "content": _b64("x=1")}

    with patch("requests.get", return_value=_make_response(200, get_body)):
        with patch("requests.put", return_value=_make_put_response(404, {"message": "Not Found"})):
            with pytest.raises(ValueError, match="not found"):
                client.commit_file(
                    repo="my-repo",
                    path="main.py",
                    new_content="x = 2\n",
                    branch="ghost-branch",
                    commit_message="fix: update x",
                )


# ── create_pull_request tests ─────────────────────────────────────────────────


def test_create_pull_request_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_pull_request POSTs correct title, body, head, and base."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    pr_response = {
        "number": 42,
        "html_url": "https://github.com/test-user/my-repo/pull/42",
        "state": "open",
        "id": 999,
    }

    with patch("requests.post", return_value=_make_response(201, pr_response)) as mock_post:
        result = client.create_pull_request(
            repo="my-repo",
            title="Auto-fix: syntax error",
            body="Added missing colon.",
            head="fix-branch",
            base="main",
        )

    assert result["number"] == 42
    assert result["html_url"] == "https://github.com/test-user/my-repo/pull/42"

    payload = mock_post.call_args.kwargs["json"]
    assert payload["title"] == "Auto-fix: syntax error"
    assert payload["body"] == "Added missing colon."
    assert payload["head"] == "fix-branch"
    assert payload["base"] == "main"
    assert payload["draft"] is False


def test_create_pull_request_uses_default_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_pull_request calls get_repo_info to resolve base when base=None."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    repo_info_body = {
        "name": "my-repo",
        "default_branch": "main",
        "private": False,
        "html_url": "https://github.com/test-user/my-repo",
    }
    pr_response = {"number": 7, "html_url": "https://github.com/test-user/my-repo/pull/7", "state": "open"}

    with patch("requests.get", return_value=_make_response(200, repo_info_body)) as mock_get:
        with patch("requests.post", return_value=_make_response(201, pr_response)) as mock_post:
            result = client.create_pull_request(
                repo="my-repo",
                title="Auto-fix",
                body="Fix applied.",
                head="fix-branch",
            )

    assert mock_get.call_count == 1
    payload = mock_post.call_args.kwargs["json"]
    assert payload["base"] == "main"
    assert result["number"] == 7


def test_create_pull_request_validation_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_pull_request raises ValueError on HTTP 422 (validation error)."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    error_body = {"message": "Validation Failed", "errors": []}
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.json.return_value = error_body

    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(ValueError, match="PR creation failed"):
            client.create_pull_request(
                repo="my-repo",
                title="Bad PR",
                body="",
                head="fix-branch",
                base="main",
            )


# ── close_pull_request tests ──────────────────────────────────────────────────


def test_close_pull_request_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """close_pull_request PATCHes state=closed and returns response dict."""
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)

    with patch("pipeline_doctor.tools.github_client.find_dotenv", return_value=""):
        with patch("pipeline_doctor.tools.github_client.load_dotenv"):
            client = GitHubClient()

    closed_body = {"number": 42, "state": "closed", "html_url": "https://github.com/test-user/my-repo/pull/42"}

    with patch("requests.patch", return_value=_make_response(200, closed_body)) as mock_patch:
        result = client.close_pull_request("my-repo", 42)

    assert result["state"] == "closed"
    assert result["number"] == 42

    payload = mock_patch.call_args.kwargs["json"]
    assert payload == {"state": "closed"}
