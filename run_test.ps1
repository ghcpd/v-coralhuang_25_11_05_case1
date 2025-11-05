Write-Output "=== Running External Dependency Vulnerability Tests (PowerShell) ==="

if (-Not (Test-Path -Path .venv)) {
    python -m venv .venv
}
# Activate the venv for PowerShell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

pytest -q --tb=short --json-report --json-report-file=raw_results.json test_runtime_failure.py

$json = @'
[
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
'@

$json | Out-File -FilePath output.json -Encoding utf8
Write-Output "=== Tests Completed. Summary in output.json ==="
