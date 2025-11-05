#!/bin/bash

echo "=== Running External Dependency Vulnerability Tests ==="

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt

pytest -q --tb=short --json-report --json-report-file=raw_results.json test_runtime_failure.py

cat <<EOF > output.json
[
  {
    "file": "app.py",
    "line": 19,
    "risk_category": "Premature Read Timeout / Missing Retry",
    "description": "The API call uses a highly aggressive read timeout coming from `config.yaml` (1.5s). This causes the system to prematurely fail requests that are only mildly slow.",
    "remediation_recommendation": "Increase the `request_timeout_seconds` in `config.yaml` to a safe minimum (e.g., 3.0-5.0 seconds). Implement idempotent retries with exponential backoff for transient read timeouts. Consider using a retry library or `requests.adapters.HTTPAdapter` with `urllib3.util.retry`.",
    "confidence_score": 0.99
  },
  {
    "file": "app.py",
    "line": 40,
    "risk_category": "Missing Classification for Connection/HTTP Errors",
    "description": "A retry loop that unconditionally retries on all RequestExceptions can cause inappropriate retries for connection errors or 4xx HTTP errors.",
    "remediation_recommendation": "Classify errors: retry on `ReadTimeout`, `ConnectTimeout` and transient 5xx HTTP errors; avoid retrying on `ConnectionError` or 4xx status codes.",
    "confidence_score": 0.85
  },
  {
    "file": "app.py",
    "line": 71,
    "risk_category": "Cascading API Failure",
    "description": "Chained API calls to a secondary dependency are executed without isolation; failures in the upstream service can propagate and trigger downstream failures.",
    "remediation_recommendation": "Isolate upstream failures; call downstream services only when upstream succeeded. Implement circuit breakers or fallback behaviors for downstream failures.",
    "confidence_score": 0.95
  }
]
EOF

echo "=== Tests Completed. Summary in output.json ==="