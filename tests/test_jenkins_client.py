"""Unit tests for JenkinsClient — all HTTP calls mocked via `responses`."""

from __future__ import annotations

import pytest
import responses as rsps
from requests.exceptions import ConnectionError as ReqConnectionError, Timeout

from pipeline_doctor.tools.jenkins_client import (
    JenkinsAuthError,
    JenkinsClient,
    JenkinsConnectionError,
    JenkinsError,
    JenkinsNotFoundError,
    JenkinsTimeoutError,
)

BASE = "http://jenkins-test:8080"


@pytest.fixture
def client() -> JenkinsClient:
    return JenkinsClient(url=BASE, user="admin", token="secret-token")


# ── get_info ──────────────────────────────────────────────────────────────────


@rsps.activate
def test_get_info_injects_version_from_header(client: JenkinsClient) -> None:
    rsps.add(
        rsps.GET,
        f"{BASE}/api/json",
        json={"description": "", "jobs": [], "mode": "NORMAL"},
        headers={"X-Jenkins": "2.440.1"},
        status=200,
    )
    info = client.get_info()
    assert info["_jenkins_version"] == "2.440.1"
    assert info["mode"] == "NORMAL"


@rsps.activate
def test_get_info_missing_header_falls_back_to_unknown(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/api/json", json={"jobs": []}, status=200)
    assert client.get_info()["_jenkins_version"] == "unknown"


# ── list_jobs ─────────────────────────────────────────────────────────────────


@rsps.activate
def test_list_jobs_returns_alphabetically_sorted(client: JenkinsClient) -> None:
    rsps.add(
        rsps.GET,
        f"{BASE}/api/json",
        json={"jobs": [{"name": "zebra"}, {"name": "alpha"}, {"name": "middle"}]},
        status=200,
    )
    assert client.list_jobs() == ["alpha", "middle", "zebra"]


@rsps.activate
def test_list_jobs_empty_returns_empty_list(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/api/json", json={"jobs": []}, status=200)
    assert client.list_jobs() == []


# ── get_job_info ──────────────────────────────────────────────────────────────


@rsps.activate
def test_get_job_info_returns_parsed_json(client: JenkinsClient) -> None:
    payload = {"name": "my-app", "color": "blue", "lastBuild": {"number": 7}}
    rsps.add(rsps.GET, f"{BASE}/job/my-app/api/json", json=payload, status=200)
    info = client.get_job_info("my-app")
    assert info["name"] == "my-app"
    assert info["lastBuild"]["number"] == 7


# ── get_latest_build_number ───────────────────────────────────────────────────


@rsps.activate
def test_get_latest_build_number_success(client: JenkinsClient) -> None:
    rsps.add(
        rsps.GET,
        f"{BASE}/job/my-app/api/json",
        json={"lastBuild": {"number": 42}},
        status=200,
    )
    assert client.get_latest_build_number("my-app") == 42


@rsps.activate
def test_get_latest_build_number_no_builds_raises(client: JenkinsClient) -> None:
    rsps.add(
        rsps.GET,
        f"{BASE}/job/my-app/api/json",
        json={"lastBuild": None},
        status=200,
    )
    with pytest.raises(ValueError, match="no builds yet"):
        client.get_latest_build_number("my-app")


# ── get_build_info ────────────────────────────────────────────────────────────


@rsps.activate
def test_get_build_info_success(client: JenkinsClient) -> None:
    payload = {"number": 42, "result": "SUCCESS", "duration": 12000}
    rsps.add(rsps.GET, f"{BASE}/job/my-app/42/api/json", json=payload, status=200)
    info = client.get_build_info("my-app", 42)
    assert info["result"] == "SUCCESS"
    assert info["number"] == 42


# ── get_build_log ─────────────────────────────────────────────────────────────


@rsps.activate
def test_get_build_log_returns_plain_text(client: JenkinsClient) -> None:
    log = "Started by admin\nBuilding...\nFinished: SUCCESS\n"
    rsps.add(rsps.GET, f"{BASE}/job/my-app/42/consoleText", body=log, status=200)
    assert client.get_build_log("my-app", 42) == log


# ── is_build_failed ───────────────────────────────────────────────────────────


@rsps.activate
def test_is_build_failed_true_on_failure(client: JenkinsClient) -> None:
    rsps.add(
        rsps.GET, f"{BASE}/job/my-app/42/api/json", json={"result": "FAILURE"}, status=200
    )
    assert client.is_build_failed("my-app", 42) is True


@pytest.mark.parametrize("result", ["SUCCESS", "ABORTED", "UNSTABLE", None])
@rsps.activate
def test_is_build_failed_false_for_non_failure(
    client: JenkinsClient, result: str | None
) -> None:
    rsps.add(
        rsps.GET,
        f"{BASE}/job/my-app/42/api/json",
        json={"result": result},
        status=200,
    )
    assert client.is_build_failed("my-app", 42) is False


# ── error handling ────────────────────────────────────────────────────────────


@rsps.activate
def test_401_raises_auth_error(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/api/json", status=401)
    with pytest.raises(JenkinsAuthError):
        client.get_info()


@rsps.activate
def test_403_raises_auth_error(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/api/json", status=403)
    with pytest.raises(JenkinsAuthError):
        client.get_info()


@rsps.activate
def test_404_raises_not_found_error(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/job/ghost/api/json", status=404)
    with pytest.raises(JenkinsNotFoundError):
        client.get_job_info("ghost")


@rsps.activate
def test_500_raises_jenkins_error(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/api/json", status=500)
    with pytest.raises(JenkinsError):
        client.get_info()


@rsps.activate
def test_connection_refused_raises_connection_error(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/api/json", body=ReqConnectionError("refused"))
    with pytest.raises(JenkinsConnectionError):
        client.get_info()


@rsps.activate
def test_timeout_raises_timeout_error(client: JenkinsClient) -> None:
    rsps.add(rsps.GET, f"{BASE}/api/json", body=Timeout("timed out"))
    with pytest.raises(JenkinsTimeoutError):
        client.get_info()
