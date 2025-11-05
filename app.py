import requests
import yaml
import time

try:
    with open('config.yaml', 'r') as f:
        CONFIG = yaml.safe_load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    CONFIG = {'api_settings': {}}

ANALYTICS_URL = CONFIG.get('api_settings', {}).get('analytics_url', '')
SECONDARY_URL = CONFIG.get('api_settings', {}).get('secondary_url', 'http://secondary.service/notify')
# Configuration: sensible defaults and clear separation of connect/read timeouts
DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = float(CONFIG.get('api_settings', {}).get('request_timeout_seconds', 3.0))


def _is_retryable(exc):
    return isinstance(exc, (requests.exceptions.ReadTimeout, requests.exceptions.Timeout))


def post_with_retries(url, json=None, connect_timeout=DEFAULT_CONNECT_TIMEOUT, read_timeout=DEFAULT_READ_TIMEOUT,
                      max_retries=3, backoff_factor=0.5):
    """Post with a simple exponential backoff retry for retryable transient errors.

    - Retries on ReadTimeout/Timeout.
    - Does not retry on ConnectionError or HTTP status errors (those should be handled by caller).
    Returns (response, attempts)
    """
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=json, timeout=(connect_timeout, read_timeout))
            resp.raise_for_status()
            return resp, attempt
        except requests.exceptions.RequestException as e:
            last_exc = e
            if _is_retryable(e) and attempt < max_retries:
                sleep_time = backoff_factor * (2 ** (attempt - 1))
                time.sleep(sleep_time)
                continue
            raise
    # If we exit loop, raise last exception
    if last_exc:
        raise last_exc
    raise RuntimeError('Unknown failure in post_with_retries')


def log_event(event_data):
    """Original vulnerable entrypoint preserved for tests.

    Attempts a single POST using configured (possibly aggressive) read timeout.
    """
    try:
        response = requests.post(ANALYTICS_URL, json=event_data, timeout=(DEFAULT_CONNECT_TIMEOUT, float(CONFIG.get('api_settings', {}).get('request_timeout_seconds', 3.0))))
        response.raise_for_status()
        return {"status": "success"}
    except requests.exceptions.ReadTimeout as e:
        print(f"Read timeout occurred: {e}. Failure is premature.")
        return {"status": "failed", "reason": f"Read Timeout: {e}"}
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "reason": str(e)}


def log_event_with_fix(event_data, fallback=None):
    """Fixed implementation with retries, backoff, and optional fallback.

    - Uses `post_with_retries` with safer read timeout and retries on ReadTimeout/Timeout.
    - On non-retryable errors, returns an informative failure without raising.
    - If `fallback` is provided (callable), it will be called to produce an alternative result when the API is unavailable.
    """
    try:
        resp, attempts = post_with_retries(ANALYTICS_URL or "http://httpbin.org/delay/2", json=event_data,
                                 connect_timeout=DEFAULT_CONNECT_TIMEOUT, read_timeout=max(DEFAULT_READ_TIMEOUT, 3.0),
                                 max_retries=3, backoff_factor=0.5)
        return {"status": "success", "attempts": attempts}
    except requests.exceptions.ReadTimeout as e:
        # Retry exhausted for read timeout
        if callable(fallback):
            try:
                return {"status": "fallback", "result": fallback(event_data)}
            except Exception:
                return {"status": "failed", "reason": "Fallback failed after ReadTimeout"}
        return {"status": "failed", "reason": f"ReadTimeout after retries: {e}"}
    except requests.exceptions.ConnectionError as e:
        # Connection errors are often immediate and may indicate network/DNS issues; avoid blind retries
        return {"status": "failed", "reason": f"ConnectionError: {e}"}
    except requests.exceptions.HTTPError as e:
        return {"status": "failed", "reason": f"HTTPError: {e.response.status_code if e.response is not None else 'unknown'}"}
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "reason": str(e)}


def chain_call_vulnerable(event_data):
    """A chain of calls without isolation — a failure in the first will bubble up and stop the chain.

    This demonstrates cascading failure.
    """
    # This call uses the same aggressive read timeout from config
    response = requests.post(ANALYTICS_URL, json=event_data, timeout=(DEFAULT_CONNECT_TIMEOUT, float(CONFIG.get('api_settings', {}).get('request_timeout_seconds', 3.0))))
    response.raise_for_status()
    # downstream call — no isolation
    requests.post(SECONDARY_URL, json={"user_event": event_data}, timeout=(DEFAULT_CONNECT_TIMEOUT, float(CONFIG.get('api_settings', {}).get('request_timeout_seconds', 3.0))))
    return {"status": "ok"}


def chain_call_with_isolation(event_data, fallback=None):
    """Isolated chain: uses the fixed logger with retries and a fallback so downstream work can continue.

    - If analytics is unavailable, run `fallback` (if provided) and continue to secondary.
    - Always swallow transient errors for downstream non-critical work.
    """
    analytics_result = log_event_with_fix(event_data, fallback=fallback)
    if analytics_result.get('status') == 'failed':
        # record locally, but continue
        local_record = {"recorded_locally": True}
    else:
        local_record = {"recorded_locally": False}

    try:
        requests.post(SECONDARY_URL, json={"user_event": event_data, "local_record": local_record}, timeout=(DEFAULT_CONNECT_TIMEOUT, max(DEFAULT_READ_TIMEOUT, 3.0)))
    except requests.exceptions.RequestException:
        # Downstream is non-critical; swallow the exception and return a best-effort response
        return {"status": "ok", "note": "secondary_unreachable", "analytics": analytics_result}

    return {"status": "ok", "analytics": analytics_result}


if __name__ == "__main__":
    print(log_event({"user_id": 101, "data": "item_view"}))
