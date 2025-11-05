import pytest
import requests
import responses

from app import log_event, log_event_with_fix, ANALYTICS_URL, chain_event, chain_event_with_fix


@responses.activate
def test_premature_read_timeout_vulnerability():
    """Vulnerable Test: Simulate a ReadTimeout when posting to analytics."""
    # Simulate ReadTimeout by raising the exception from a callback
    def timeout_callback(request):
        raise requests.exceptions.ReadTimeout('Read timed out (1.5s)')

    responses.add_callback(responses.POST, ANALYTICS_URL, callback=lambda req: timeout_callback(req))

    result = log_event({"key": "value"})
    assert result["status"] == "failed"
    assert "Read Timeout" in result["reason"]


@responses.activate
def test_premature_read_timeout_fix():
    """Validation Test: Ensure the fixed function (with retries) succeeds on second attempt."""
    # First call: raise ReadTimeout; Second call: return 200 OK
    def timeout_then_success(request):
        # Pop first callback to simulate one-time timeout
        if len(responses.calls) == 0:
            raise requests.exceptions.ReadTimeout('Read timed out (1.5s)')
        return (200, {}, "{\"ok\": true}")

    # Add a callback that will time out the first time, then succeed
    responses.add_callback(responses.POST, ANALYTICS_URL, callback=lambda req: timeout_then_success(req))
    responses.add(responses.POST, ANALYTICS_URL, json={"ok": True}, status=200)

    result = log_event_with_fix({"key": "value"}, max_retries=2, read_timeout=3.0)
    assert result["status"] == "success"
    assert result["attempts"] <= 2


@responses.activate
def test_connection_error_not_retried():
    """Ensure ConnectionError is not aggressively retried and is surfaced as ConnectionError."""
    def connection_error_callback(request):
        raise requests.exceptions.ConnectionError('Failed to connect')

    responses.add_callback(responses.POST, ANALYTICS_URL, callback=lambda req: connection_error_callback(req))

    result = log_event_with_fix({"key": "value"}, max_retries=2)
    assert result["status"] == "failed"
    assert result["reason"] == "ConnectionError"


@responses.activate
def test_cascading_failure_vulnerable():
    """Demonstrate that the vulnerable chain_event propagates upstream failure to caller."""
    def timeout_callback(request):
        raise requests.exceptions.ReadTimeout('Read timed out (1.5s)')

    responses.add_callback(responses.POST, ANALYTICS_URL, callback=lambda req: timeout_callback(req))

    with pytest.raises(RuntimeError):
        chain_event({"key": "value"})


@responses.activate
def test_cascading_failure_with_fix():
    """Ensure fixed chain isolates failures and returns degraded mode on analytics failure."""
    def timeout_callback(request):
        raise requests.exceptions.ReadTimeout('Read timed out (1.5s)')

    responses.add_callback(responses.POST, ANALYTICS_URL, callback=lambda req: timeout_callback(req))

    result = chain_event_with_fix({"key": "value"}, max_retries=1)
    assert result["status"] == "degraded"
    assert result["reason"] == "analytics_failed"
