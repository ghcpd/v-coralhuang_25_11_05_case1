import requests
import yaml
import time
import logging

logging.basicConfig(level=logging.INFO)

try:
    with open('config.yaml', 'r') as f:
        CONFIG = yaml.safe_load(f)
except Exception as e:
    logging.error(f"Error loading config: {e}")
    CONFIG = {'api_settings': {}}

ANALYTICS_URL = CONFIG.get('api_settings', {}).get('analytics_url', '')
TIMEOUT = CONFIG.get('api_settings', {}).get('request_timeout_seconds', 3.0)


def log_event(event_data):
    try:
        response = requests.post(ANALYTICS_URL, json=event_data, timeout=(5.0, TIMEOUT))
        response.raise_for_status()
        return {"status": "success"}
    except requests.exceptions.ReadTimeout as e:
        logging.warning(f"Read timeout occurred: {e}. Failure is premature.")
        return {"status": "failed", "reason": "Premature Read Timeout"}
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "reason": str(e)}


def _is_retryable_exception(exc):
    # Read/Connect timeouts are commonly transient and safe to retry.
    if isinstance(exc, (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout)):
        return True
    # HTTP errors may be retried for 5xx responses but not for 4xx.
    if isinstance(exc, requests.exceptions.HTTPError):
        try:
            code = exc.response.status_code
            return 500 <= code < 600
        except Exception:
            return False
    return False


def log_event_with_fix(event_data, max_retries=3, backoff_factor=0.5):
    """Robust implementation: higher read timeout, finite retry loop with exponential backoff,
    and classification of retryable errors. Tries to avoid retrying on connection errors which
    often indicate persistent network issues.
    """
    attempt = 0
    read_timeout = max(TIMEOUT, 3.0)  # ensure a sensible minimum
    while attempt < max_retries:
        try:
            resp = requests.post(ANALYTICS_URL, json=event_data, timeout=(5.0, read_timeout))
            resp.raise_for_status()
            return {"status": "success", "attempts": attempt + 1}
        except requests.exceptions.RequestException as e:
            logging.warning(f"Attempt {attempt+1} failed with: {e}")
            # Do not retry on ConnectionError by default (could be extended)
            if isinstance(e, requests.exceptions.ConnectionError):
                return {"status": "failed", "reason": str(e), "attempts": attempt + 1}
            if not _is_retryable_exception(e) and not isinstance(e, requests.exceptions.HTTPError):
                return {"status": "failed", "reason": str(e), "attempts": attempt + 1}
            attempt += 1
            if attempt >= max_retries:
                break
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            time.sleep(sleep_time)
    return {"status": "failed", "reason": "Failed after retries", "attempts": attempt}


def call_two_services(primary_payload, secondary_payload):
    """Example of chained API calls with isolation. If primary fails, we do not call secondary and
    instead return a fallback or a partial-success indicator.
    """
    try:
        resp = requests.post(ANALYTICS_URL, json=primary_payload, timeout=(5.0, max(TIMEOUT, 3.0)))
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Primary call failed: {e}. Aborting secondary call and returning fallback.")
        return {"status": "fallback", "reason": str(e)}

    # Only if primary succeeded we call the secondary downstream service
    SECONDARY_URL = CONFIG.get('api_settings', {}).get('secondary_url', '')
    try:
        r2 = requests.post(SECONDARY_URL, json=secondary_payload, timeout=(5.0, max(TIMEOUT, 3.0)))
        r2.raise_for_status()
        return {"status": "ok"}
    except requests.exceptions.RequestException as e:
        logging.error(f"Secondary call failed: {e}. Returning partial success.")
        return {"status": "partial_success", "reason": str(e)}


if __name__ == "__main__":
    print(log_event({"user_id": 101, "data": "item_view"}))