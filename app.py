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
TIMEOUT = CONFIG.get('api_settings', {}).get('request_timeout_seconds', 3.0)

def log_event(event_data):
    try:
        response = requests.post(ANALYTICS_URL, json=event_data, timeout=(5.0, TIMEOUT))
        response.raise_for_status()
        return {"status": "success"}
    except requests.exceptions.ReadTimeout as e:
        print(f"Read timeout occurred: {e}. Failure is premature.")
        return {"status": "failed", "reason": "Premature Read Timeout"}
    except requests.exceptions.RequestException as e:
        return {"status": "failed", "reason": str(e)}

def log_event_with_fix(event_data):
    """Simulates the fix: increased timeout and a simple retry."""
    MAX_RETRIES = 2
    for attempt in range(MAX_RETRIES):
        try:
            requests.post("http://httpbin.org/delay/2", json=event_data, timeout=(5.0, 3.0))
            return {"status": "success", "attempts": attempt + 1}
        except requests.exceptions.ReadTimeout as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            raise e
    return {"status": "failed", "reason": "Failed after retries"}

if __name__ == "__main__":
    print(log_event({"user_id": 101, "data": "item_view"}))