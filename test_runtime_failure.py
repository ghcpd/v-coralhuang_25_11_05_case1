import pytest
import requests
import respx
import time

from app import log_event, log_event_with_fix, ANALYTICS_URL

@respx.mock
def test_premature_read_timeout_vulnerability():
    """Vulnerable Test: Simulate a 2.0s slow API response vs a 1.5s timeout."""
    respx.post(ANALYTICS_URL).mock(side_effect=requests.exceptions.ReadTimeout('Read timed out (1.5s)'))
    result = log_event({"key": "value"})
    assert result["status"] == "failed"
    assert "Premature Read" in result["reason"] or "Read Timeout" in result["reason"]

@respx.mock
def test_premature_read_timeout_fix():
    """Validation Test: Ensure the fixed function with retry succeeds against a transient ReadTimeout."""
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise requests.exceptions.ReadTimeout("first attempt timed out")
        return respx.Response(200, json={"ok": True})

    respx.post(ANALYTICS_URL).mock(side_effect=handler)
    result = log_event_with_fix({"key": "value"}, max_retries=2, backoff_factor=0)
    assert result["status"] == "success"
    assert result["attempts"] == 2

@respx.mock
def test_connection_error_no_retry():
    """Ensure connection errors are not retried by default and return quickly."""
    respx.post(ANALYTICS_URL).mock(side_effect=requests.exceptions.ConnectionError("Conn failed"))
    result = log_event_with_fix({"key": "value"}, max_retries=3)
    assert result["status"] == "failed"
    assert "Connection" in result["reason"]

@respx.mock
def test_cascading_api_failure_isolated():
    """Upstream failure should not cascade to downstream service."""
    # Primary fails
    respx.post(ANALYTICS_URL).mock(side_effect=requests.exceptions.ReadTimeout("timeout"))
    # Secondary would succeed if called, but should not be called
    respx.post("http://api.secondary.io/submit").mock(return_value=respx.Response(200))

    from app import call_two_services
    result = call_two_services({"k": "v"}, {"k2": "v2"})
    assert result["status"] == "fallback"

@respx.mock
def test_cascading_api_success():
    """When primary succeeds, confirm the downstream call is made and returns ok."""
    respx.post(ANALYTICS_URL).mock(return_value=requests.Response(200))
    respx.post("http://api.secondary.io/submit").mock(return_value=respx.Response(200))

    from app import call_two_services
    result = call_two_services({"k": "v"}, {"k2": "v2"})
    assert result["status"] == "ok"

@respx.mock
def test_retry_on_5xx_http_error():
    """Transient 5xx errors should be retried and succeeded with retry logic."""
    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return respx.Response(500, json={"error": "server error"})
        return respx.Response(200, json={"ok": True})

    respx.post(ANALYTICS_URL).mock(side_effect=handler)
    result = log_event_with_fix({"key": "value"}, max_retries=2, backoff_factor=0)
    assert result["status"] == "success"
    assert result["attempts"] == 2
