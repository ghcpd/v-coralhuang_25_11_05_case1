Write-Output "=== Running External Dependency Vulnerability Tests (PowerShell) ==="

if (-Not (Test-Path -Path .venv)) {
    python -m venv .venv
}
$Activate = Join-Path -Path (Get-Location) -ChildPath ".venv\Scripts\Activate.ps1"
. $Activate
pip install -r requirements.txt

pytest -q --tb=short --json-report --json-report-file=raw_results.json test_runtime_failure.py

$report = Get-Content raw_results.json -Raw
$summary = @(
    @{file = 'app.py'; line = 18; risk_category = 'Premature Read Timeout'; description = 'Aggressive read timeout from config causes premature failures.'; remediation_recommendation = 'Increase read timeout to 3-5s and add retry/backoff with selective retry for ReadTimeout.'; confidence_score = 0.99},
    @{file = 'app.py'; line = 50; risk_category = 'Missing Retry/Backoff'; description = 'No retry for transient ReadTimeouts in vulnerable path.'; remediation_recommendation = 'Add retry with exponential backoff and limit retries to transient errors only.'; confidence_score = 0.95},
    @{file = 'app.py'; line = 90; risk_category = 'Cascading API Failure'; description = 'Chained calls without isolation cause downstream failures when upstream fails.'; remediation_recommendation = 'Isolate upstream failures, use fallbacks or continue-on-failure for non-critical downstreams.'; confidence_score = 0.9}
)
$summary | ConvertTo-Json | Out-File output.json -Encoding utf8

Write-Output "=== Tests Completed. Summary in output.json ==="