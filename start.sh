#!/usr/bin/env bash
# Start the music bot on Linux. The launcher creates .venv and installs
# everything it needs on first run.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10+ is required but python3 was not found."
    echo "Install it with your package manager (e.g. sudo apt-get install python3 python3-venv)"
    echo "or download it from https://www.python.org/downloads/"
    exit 1
fi

exec python3 launcher.py "$@"
