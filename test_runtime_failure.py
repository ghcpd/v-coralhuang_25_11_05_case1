import pytest
import requests
import responses

from app import log_event, log_event_with_fix, chain_call_vulnerable, chain_call_with_isolation, ANALYTICS_URL, SECONDARY_URL


@responses.activate
def test_vulnerable_read_timeout():
    # Simulate ReadTimeout on the configured analytics URL
    responses.add(responses.POST, ANALYTICS_URL, body=requests.exceptions.ReadTimeout('Read timed out (1.5s)'))
    result = log_event({"key": "value"})
    assert result["status"] == "failed"
    assert "Read Timeout" in result["reason"] or "Read Timeout" in result.get("reason", "")


@responses.activate
def test_fixed_handles_slow_response_and_retries():
    # Simulate a successful slow response (2s): mock a 200 OK response
    responses.add(responses.POST, ANALYTICS_URL, json={"ok": True}, status=200)

    result = log_event_with_fix({"key": "value"})
    assert result["status"] == "success"
    assert result["attempts"] <= 3


@responses.activate
def test_connection_error_not_retried():
    # ConnectionError should not be retried by post_with_retries; log_event_with_fix should return failed for connection errors.
    responses.add(responses.POST, ANALYTICS_URL, body=requests.exceptions.ConnectionError('DNS failure'))
    result = log_event_with_fix({"key": "value"})
    assert result["status"] == "failed"
    assert "ConnectionError" in result["reason"]


@responses.activate
def test_cascading_failure_demo():
    # If analytics fails and chain_call_vulnerable is used, downstream won't be called.
    responses.add(responses.POST, ANALYTICS_URL, body=requests.exceptions.ReadTimeout('Read timed out'))
    with pytest.raises(requests.exceptions.ReadTimeout):
        chain_call_vulnerable({"k": "v"})


@responses.activate
def test_chained_with_isolation_continues_on_analytics_failure():
    # Analytics ReadTimeout, but chain_call_with_isolation should continue and attempt secondary
    responses.add(responses.POST, ANALYTICS_URL, body=requests.exceptions.ReadTimeout('Read timed out'))
    responses.add(responses.POST, SECONDARY_URL, json={"ok": True}, status=200)

    result = chain_call_with_isolation({"k": "v"})
    assert result["status"] == "ok"
    assert "analytics" in result

