# PowerShell equivalent of run_test.sh for Windows

Write-Host "=== Running External Dependency Vulnerability Tests ===" -ForegroundColor Cyan

$python = "C:/Users/v-coralhuang/AppData/Local/Programs/Python/Python310/python.exe"

# Check if requirements are installed
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $python -m pip install -q -r requirements.txt

# Run tests
Write-Host "Running test suite..." -ForegroundColor Yellow
& $python -m pytest -q --tb=short --json-report --json-report-file=raw_results.json test_runtime_failure.py

Write-Host "=== Tests Completed. Results in raw_results.json and output.json ===" -ForegroundColor Green
