#!/usr/bin/env bash
# Start the music bot on macOS (double-click in Finder or run in Terminal).
# The launcher creates .venv and installs everything it needs on first run.
cd "$(dirname "$0")" || exit 1

# Homebrew is not on PATH when Finder opens this file in a fresh shell.
for dir in /opt/homebrew/bin /usr/local/bin; do
    case ":$PATH:" in *":$dir:"*) ;; *) [ -d "$dir" ] && PATH="$dir:$PATH" ;; esac
done
export PATH

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    echo "Python 3.10+ is required."
    echo "Install it from https://www.python.org/downloads/ or with Homebrew: brew install python"
    read -r -p "Press Enter to close..." _
    exit 1
fi

python3 launcher.py "$@"
status=$?
if [ $status -ne 0 ]; then
    read -r -p "Press Enter to close..." _
fi
exit $status
