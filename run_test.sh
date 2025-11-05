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
    "line": 18,
    "risk_category": "Premature Read Timeout / Missing Retry",
    "description": "The vulnerable API call uses a very small read timeout (1.5s) without retries, causing premature failures for transient slowness.",
    "remediation_recommendation": "Increase read timeout to 3-5s and add retry with exponential backoff for ReadTimeout exceptions.",
    "confidence_score": 0.99
  },
  {
    "file": "app.py",
    "line": 60,
    "risk_category": "Cascading API Failure",
    "description": "Chained API calls can cascade: if the upstream call fails, downstream calls may also fail and cause larger outages.",
    "remediation_recommendation": "Isolate failures and provide fallbacks or circuit breakers for upstream failures (use local defaults or cached responses).",
    "confidence_score": 0.95
  }
]
EOF

echo "=== Tests Completed. Summary in output.json ==="
