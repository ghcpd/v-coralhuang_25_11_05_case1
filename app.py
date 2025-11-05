import requests
import yaml
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# Load configuration
try:
    with open('config.yaml', 'r') as f:
        CONFIG = yaml.safe_load(f)
except Exception as e:
    logger.warning("Error loading config: %s", e)
    CONFIG = {'api_settings': {}}

ANALYTICS_URL = CONFIG.get('api_settings', {}).get('analytics_url', '')
# Upgrade configuration defaults to safer values
_CONNECT_TIMEOUT_DEFAULT = 5.0
_READ_TIMEOUT_DEFAULT = 3.0
TIMEOUT = CONFIG.get('api_settings', {}).get('request_timeout_seconds', _READ_TIMEOUT_DEFAULT)


def _post_with_retries(url, json=None, connect_timeout=_CONNECT_TIMEOUT_DEFAULT, read_timeout=_READ_TIMEOUT_DEFAULT,
                       max_retries=3, backoff_factor=0.5, retry_on_status=(500,)):
    """Generic POST with retry behavior. Retries on ReadTimeout and on configurable 5xx responses.

    - Does NOT retry on ConnectionError by default (treat as an infrastructure outage).
    - Retries on ReadTimeout and server 5xx status codes.
    - Applies exponential backoff with jitter.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=json, timeout=(connect_timeout, read_timeout))
            # If status code indicates server error and should be retried
            if resp.status_code >= retry_on_status[0] and resp.status_code < 600:
                # Only retry for server errors
                logger.warning("Server returned %s for %s; attempt %s/%s", resp.status_code, url, attempt, max_retries)
                if attempt == max_retries:
                    resp.raise_for_status()
                else:
                    sleep_time = backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)
                    continue
            resp.raise_for_status()
            return resp
        except requests.exceptions.ReadTimeout as e:
            # Recommended to retry on read timeouts (transient slowness)
            logger.warning("Read timeout for %s: %s; attempt %s/%s", url, e, attempt, max_retries)
            if attempt == max_retries:
                raise
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            time.sleep(sleep_time)
        except requests.exceptions.ConnectionError as e:
            # Connection errors often mean network unreachable; do not retry aggressively
            logger.error("Connection error for %s: %s; aborting", url, e)
            raise


# Vulnerable function: preserves original vulnerable behavior but keeps it as-is for tests
def log_event(event_data):
    try:
        response = requests.post(ANALYTICS_URL, json=event_data, timeout=(5.0, TIMEOUT))
        response.raise_for_status()
        return {"status": "success"}
    except requests.exceptions.ReadTimeout as e:
        logger.error("Read timeout occurred: %s. Failure is premature.", e)
        return {"status": "failed", "reason": "Premature Read Timeout"}
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "reason": str(e)}


# Improved function: better timeouts, retry loop with exponential backoff, and error differentiation
def log_event_with_fix(event_data, max_retries=3, connect_timeout=_CONNECT_TIMEOUT_DEFAULT, read_timeout=_READ_TIMEOUT_DEFAULT):
    try:
        resp = _post_with_retries(ANALYTICS_URL, json=event_data, connect_timeout=connect_timeout,
                                  read_timeout=read_timeout, max_retries=max_retries)
        return {"status": "success", "attempts": 1}
    except requests.exceptions.ReadTimeout as e:
        # Communicate the reason clearly
        logger.error("Failed after read timeouts: %s", e)
        return {"status": "failed", "reason": "ReadTimeout"}
    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error that should be handled differently: %s", e)
        return {"status": "failed", "reason": "ConnectionError"}
    except requests.exceptions.RequestException as e:
        logger.error("HTTP error calling analytics: %s", e)
        return {"status": "failed", "reason": str(e)}


# Example of chained API calls that need isolation/fallback
def chain_event(event_data):
    """A function that chains two API calls. The unsafe version propagates exceptions; the fixed
    version isolates failures and uses fallbacks.
    """
    # Call 1: analytics
    a_res = log_event(event_data)
    if a_res.get("status") != "success":
        # Vulnerable behavior: raise or propagate failure
        raise RuntimeError("analytics failed")

    # Call 2: hypothetical downstream service
    try:
        secondary_resp = requests.post("http://api.downstream.svc/process", json=event_data, timeout=(5.0, TIMEOUT))
        secondary_resp.raise_for_status()
        return {"status": "success"}
    except requests.exceptions.RequestException as e:
        # propagate
        raise


# Fixed chain that isolates failures and provides a fallback
def chain_event_with_fix(event_data, max_retries=3):
    # Try analytics with retries
    analytics = log_event_with_fix(event_data, max_retries=max_retries)
    if analytics.get("status") != "success":
        # Isolate failure and continue with degraded mode
        logger.warning("Analytics failed, continuing in degraded mode: %s", analytics)
        # In degraded mode, we avoid calling downstream or call with alternative data
        return {"status": "degraded", "reason": "analytics_failed"}

    # Call downstream with protected retries
    try:
        _post_with_retries("http://api.downstream.svc/process", json=event_data, max_retries=2)
        return {"status": "success"}
    except requests.exceptions.RequestException as e:
        logger.error("Downstream failed: %s", e)
        # Fallback: record local message or queue for async processing
        return {"status": "degraded", "reason": "downstream_failed"}


if __name__ == "__main__":
    logger.info(log_event({"user_id": 101, "data": "item_view"}))
