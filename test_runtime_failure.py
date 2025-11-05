import pytest
import requests
import responses
import json

from app import log_event, log_event_with_fix, chain_api_calls, chain_api_calls_with_fallback, ANALYTICS_URL

@responses.activate
def test_premature_read_timeout_vulnerability():
    # Simulate a slow API by raising a requests ReadTimeout
    responses.add(responses.POST, ANALYTICS_URL, body=requests.exceptions.ReadTimeout('Read timed out (1.5s)'))

    result = log_event({"key": "value"})
    assert result["status"] == "failed"
    assert "Read Timeout" in result["reason"]

@responses.activate
def test_premature_read_timeout_fix():
    # Simulate transient ReadTimeout on first call, success on second
    call_count = {'n': 0}

    def request_callback(request):
        call_count['n'] += 1
        if call_count['n'] == 1:
            raise requests.exceptions.ReadTimeout('Read timed out')
        return (200, {'Content-Type': 'application/json'}, json.dumps({'ok': True}))

    responses.add_callback(responses.POST, ANALYTICS_URL, callback=request_callback)

    result = log_event_with_fix({"key": "value"})
    assert result["status"] == "success"
    assert result["attempts"] <= 3

@responses.activate
def test_connection_error_not_retried_and_fails():
    responses.add(responses.POST, ANALYTICS_URL, body=requests.exceptions.ConnectionError('Connection refused'))
    result = log_event_with_fix({"key": "value"})
    assert result["status"] == "failed"
    assert "Connection error" in result["reason"]

@responses.activate
def test_cascading_failure_vulnerable_chain():
    # Upstream returns a 500 which should cause chain_api_calls to raise
    responses.add(responses.POST, ANALYTICS_URL, json={'error': 'upstream failed'}, status=500)
    downstream_url = ANALYTICS_URL + "/transform"
    responses.add(responses.POST, downstream_url, json={'ok': True}, status=200)

    with pytest.raises(requests.exceptions.HTTPError):
        chain_api_calls({"user": 1})

@responses.activate
def test_cascading_failure_fixed_chain():
    # Upstream fails; fixed chain should return fallback and still call downstream
    responses.add(responses.POST, ANALYTICS_URL, json={'error': 'upstream failed'}, status=500)
    downstream_url = ANALYTICS_URL + "/transform"
    responses.add(responses.POST, downstream_url, json={'ok': True, 'processed': True}, status=200)

    result = chain_api_calls_with_fallback({"user": 1})
    assert result["status"] == "success"
    assert result["result"][0]["id"] == "local-default"

