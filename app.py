import requests
import yaml
import time
from typing import Dict, Any

try:
    with open('config.yaml', 'r') as f:
        CONFIG = yaml.safe_load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    CONFIG = {'api_settings': {}}

ANALYTICS_URL = CONFIG.get('api_settings', {}).get('analytics_url', '')
CONNECT_TIMEOUT = CONFIG.get('api_settings', {}).get('connect_timeout_seconds', 5.0)
READ_TIMEOUT = CONFIG.get('api_settings', {}).get('request_timeout_seconds', 3.0)
MAX_RETRIES = CONFIG.get('api_settings', {}).get('max_retries', 3)
BACKOFF_FACTOR = CONFIG.get('api_settings', {}).get('backoff_factor', 1.0)


def log_event(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Vulnerable implementation: small read timeout and no retries.
    """
    try:
        response = requests.post(ANALYTICS_URL, json=event_data, timeout=(CONNECT_TIMEOUT, 1.5))
        response.raise_for_status()
        return {"status": "success"}
    except requests.exceptions.ReadTimeout as e:
        print(f"Read timeout occurred: {e}. Failure is premature.")
        return {"status": "failed", "reason": "Read Timeout"}
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "reason": str(e)}


def log_event_with_fix(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fixed implementation: sensible read/connect timeouts, retry loop with backoff,
    and explicit decision on which exceptions to retry.
    """
    session = requests.Session()
    attempt = 0

    while attempt < MAX_RETRIES:
        try:
            attempt += 1
            response = session.post(ANALYTICS_URL, json=event_data, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            response.raise_for_status()
            return {"status": "success", "attempts": attempt}
        except requests.exceptions.ReadTimeout as e:
            # These are safe to retry (transient slowness)
            if attempt < MAX_RETRIES:
                sleep_time = BACKOFF_FACTOR * (2 ** (attempt - 1))
                time.sleep(sleep_time)
                continue
            return {"status": "failed", "reason": "Read Timeout after retries"}
        except requests.exceptions.ConnectionError as e:
            # Connection errors can indicate an immediate failure; do not retry indefinitely.
            return {"status": "failed", "reason": "Connection error: " + str(e)}
        except requests.exceptions.HTTPError as e:
            # For 5xx, we may retry. For 4xx, fail immediately.
            status_code = e.response.status_code if e.response is not None else None
            if status_code and 500 <= status_code < 600 and attempt < MAX_RETRIES:
                time.sleep(BACKOFF_FACTOR * (2 ** (attempt - 1)))
                continue
            return {"status": "failed", "reason": f"HTTP error: {status_code}"}
        except requests.exceptions.RequestException as e:
            return {"status": "failed", "reason": str(e)}

    return {"status": "failed", "reason": "Failed after retries"}


def chain_api_calls(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Example of chained calls: first call to primary API, then call to downstream service.
    The vulnerable version would not isolate failures.
    """
    # First call
    r1 = requests.post(ANALYTICS_URL, json=payload, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    r1.raise_for_status()

    # Dependent call (could cascade)
    downstream_url = ANALYTICS_URL + "/transform"
    r2 = requests.post(downstream_url, json={"id": r1.json().get("id")}, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    r2.raise_for_status()
    return {"status": "success", "result": (r1.json(), r2.json())}


def chain_api_calls_with_fallback(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fixed: if upstream fails, return a safe fallback instead of failing downstream.
    """
    try:
        r1 = requests.post(ANALYTICS_URL, json=payload, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r1.raise_for_status()
        upstream_data = r1.json()
    except Exception as e:
        # Fallback: use a local default instead of failing the whole flow
        upstream_data = {"id": "local-default", "note": "upstream-unavailable"}

    try:
        downstream_url = ANALYTICS_URL + "/transform"
        r2 = requests.post(downstream_url, json={"id": upstream_data.get("id")}, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r2.raise_for_status()
        return {"status": "success", "result": (upstream_data, r2.json())}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}


if __name__ == "__main__":
    print(log_event({"user_id": 101, "data": "item_view"}))
