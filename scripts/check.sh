#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python -m ruff check wecli tests
python -m ruff format --check wecli tests
python -m compileall -q wecli
python -m unittest discover -s tests -v
