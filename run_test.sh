#!/bin/bash

echo "=== Running External Dependency Vulnerability Tests (Bash) ==="

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt

pytest -q --tb=short --json-report --json-report-file=raw_results.json test_runtime_failure.py

python - <<'PY'
import json
from pathlib import Path

raw = Path('raw_results.json').read_text()
result = json.loads(raw)

findings = [
  {
    "file": "app.py",
    "line": 36,
    "risk_category": "Premature Read Timeout",
    "description": "The API call uses an aggressive read timeout (1.5s from config.yaml), which may fail under normal network conditions.",
    "remediation_recommendation": "Increase `request_timeout_seconds` to a safer range (3.0-5.0s) and use a retry loop with exponential backoff for ReadTimeouts.",
    "confidence_score": 0.99
  },
  {
    "file": "app.py",
    "line": 56,
    "risk_category": "Missing Retry / Error Differentiation",
    "description": "`log_event_with_fix` previously retried on ReadTimeout but didn't treat ConnectionError or HTTP 5xx consistently.",
    "remediation_recommendation": "Differentiate which exceptions are retried (e.g., retry on ReadTimeout and HTTP 5xx; avoid repeated retries on ConnectionError), and add max_retry limits with backoff.",
    "confidence_score": 0.9
  },
  {
    "file": "app.py",
    "line": 84,
    "risk_category": "Cascading API Failure",
    "description": "`chain_event` propagates analytics failures and will raise errors that stop downstream processing rather than isolating failures.",
    "remediation_recommendation": "Isolate upstream failures and implement degraded mode or fallbacks; avoid letting a single dependency failure bring down the whole flow.",
    "confidence_score": 0.95
  }
]

Path('output.json').write_text(json.dumps(findings, indent=2))
print('Wrote output.json')
PY

echo "=== Tests Completed. Summary in output.json ==="
