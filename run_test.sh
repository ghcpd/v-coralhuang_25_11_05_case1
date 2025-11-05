#!/bin/bash

echo "=== Running External Dependency Vulnerability Tests ==="

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt

pytest -q --tb=short --json-report --json-report-file=raw_results.json test_runtime_failure.py

echo "=== Tests Completed. Results in raw_results.json and output.json ===" 