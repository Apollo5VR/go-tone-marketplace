#!/bin/bash
# Go-Tone Marketplace Test Runner
# Usage: ./tests/run.sh
cd "$(dirname "$0")/.."
.venv/bin/python tests/test_api_live.py