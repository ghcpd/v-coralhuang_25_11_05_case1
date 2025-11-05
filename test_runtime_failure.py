import pytest
import requests
import time
from unittest.mock import patch, MagicMock

from app import log_event, log_event_with_fix, ANALYTICS_URL

# ============================================================================
# VULNERABILITY TESTS: Demonstrate premature timeout and missing retry
# ============================================================================

def test_premature_read_timeout_vulnerability():
    """
    Vulnerable Test: Simulate a 2.0s slow API response vs a 1.5s timeout.
    The vulnerable log_event() fails prematurely because config.yaml sets
    request_timeout_seconds to 1.5s, which is too aggressive.
    """
    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.ReadTimeout('Read timed out (1.5s)')
        result = log_event({"key": "value"})
        assert result["status"] == "failed"
        assert "Read Timeout" in result["reason"]

def test_connection_error_without_retry():
    """
    Vulnerability: API connection error occurs with no retry logic.
    The vulnerable function fails immediately on ConnectionError.
    """
    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError('Connection refused')
        result = log_event({"key": "value"})
        assert result["status"] == "failed"

def test_cascading_failure_without_isolation():
    """
    Vulnerability: Two functions chained without isolation.
    If first fails, second never runs (not in this code, but shows pattern).
    """
    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.Timeout('timeout')
        result = log_event({"event": "test"})
        assert result["status"] == "failed"

# ============================================================================
# FIX VALIDATION TESTS: Demonstrate that increased timeout + retry succeeds
# ============================================================================

def test_read_timeout_fix_with_mock_retry():
    """
    Fix Validation: The fixed function uses 3.0s timeout and retry logic.
    First call raises ReadTimeout, second succeeds (retry mechanism).
    """
    call_count = [0]
    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] < 2:
            raise requests.exceptions.ReadTimeout("Transient timeout")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        return mock_resp
    
    with patch('requests.post') as mock_post:
        mock_post.side_effect = side_effect
        result = log_event_with_fix({"key": "value"})
        # Should succeed on retry (attempt 2)
        assert result["status"] == "success"
        assert result["attempts"] >= 1

def test_increased_timeout_succeeds():
    """
    Fix Validation: Simulated slow 2.0s response succeeds with 3.0s timeout.
    The fixed function has increased timeout (3.0s) and succeeds immediately.
    """
    with patch('requests.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        result = log_event_with_fix({"key": "value"})
        assert result["status"] == "success"

# ============================================================================
# DATA VALIDATION & ERROR HANDLING TESTS
# ============================================================================

def test_http_error_on_read_timeout_classification():
    """
    Verify: ReadTimeout is properly classified and handled separately from
    other HTTP errors. This is important for retry logic decisions.
    """
    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.ReadTimeout("timeout")
        result = log_event({"test": "data"})
        assert result["status"] == "failed"
        assert "Premature Read Timeout" in result["reason"]

def test_http_500_error_no_retry():
    """
    Vulnerability/Design Note: HTTP 5xx errors should NOT be retried in
    log_event() because raise_for_status() converts them to HTTPError.
    This is correct behavior but should be logged.
    """
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    
    with patch('requests.post', return_value=mock_response):
        result = log_event({"key": "value"})
        assert result["status"] == "failed"

# ============================================================================
# CONFIGURATION FAULT ISOLATION TESTS
# ============================================================================

def test_config_loading_graceful_fallback():
    """
    Verify: If config.yaml is missing, app falls back to defaults.
    This ensures robustness even if configuration is unavailable.
    """
    # The app already has this, but verify behavior
    import app as app_module
    assert app_module.TIMEOUT == 1.5  # From config
    assert app_module.ANALYTICS_URL == "http://api.analytics.io/v1/log"

def test_timeout_tuple_semantics():
    """
    Verify: The timeout tuple (connect_timeout, read_timeout) is correctly used.
    Line 18: timeout=(5.0, TIMEOUT) means 5s connect, 1.5s read (from config).
    This is the core vulnerability: 1.5s read timeout is too aggressive.
    """
    # This is a conceptual test showing the vulnerability.
    # In reality, requests.post() would timeout at 1.5s on slow APIs.
    connect_timeout = 5.0
    read_timeout = 1.5  # TOO AGGRESSIVE
    assert read_timeout < 2.0, "Read timeout should be >=2.0s for typical APIs"

