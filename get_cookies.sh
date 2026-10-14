#!/bin/bash

# YouTube Cookie Extractor Script for Pop!OS
# This script extracts YouTube cookies from Firefox for yt-dlp

echo "🍪 YouTube Cookie Extractor for Firefox"
echo "=========================================="

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    echo "💡 Install it with: sudo apt install python3"
    exit 1
fi

# Check if Firefox is installed
if ! command -v firefox &> /dev/null; then
    echo "❌ Firefox is not installed"
    echo "💡 Install it with: sudo apt install firefox"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRACTOR_SCRIPT="$SCRIPT_DIR/extract_cookies.py"

# Check if extractor script exists
if [ ! -f "$EXTRACTOR_SCRIPT" ]; then
    echo "❌ Cookie extractor script not found: $EXTRACTOR_SCRIPT"
    exit 1
fi

echo "📋 Instructions:"
echo "1. Make sure you're logged into YouTube in Firefox"
echo "2. Close Firefox completely (check with: pgrep firefox)"
echo "3. This script will extract cookies and save them as cookies.txt"
echo ""

# Check if Firefox is running
if pgrep -x "firefox" > /dev/null; then
    echo "⚠️  Firefox is currently running!"
    echo "🔍 Running Firefox processes:"
    pgrep -a -x "firefox"
    echo ""
    echo "Please close Firefox completely before continuing:"
    echo "   • Close all Firefox windows"
    echo "   • Or run: pkill firefox"
    echo ""
    read -p "Press Enter to continue, or Ctrl+C to cancel..."
fi

# Check if Firefox is still running
if pgrep -x "firefox" > /dev/null; then
    echo "❌ Firefox is still running! Please close it first."
    exit 1
fi

echo "🍪 Extracting cookies..."
echo ""

# Run the cookie extractor with improved profile detection
python3 "$EXTRACTOR_SCRIPT" --output cookies.txt

# Check if extraction was successful
if [ $? -eq 0 ] && [ -f "cookies.txt" ]; then
    echo ""
    echo "✅ Success! Cookies extracted to: cookies.txt"
    echo ""
    echo "📝 Next steps:"
    echo "1. Add this line to your config.txt:"
    echo "   cookie_file=cookies.txt"
    echo ""
    echo "2. Move cookies.txt to your bot directory if needed"
    echo ""
    echo "⚠️  Important:"
    echo "   • Keep cookies.txt secure - it contains your login data"
    echo "   • Regenerate periodically as cookies expire"
    echo "   • Delete old cookies.txt before regenerating"
else
    echo ""
    echo "❌ Cookie extraction failed"
    echo "💡 Troubleshooting:"
    echo "   • Make sure you're logged into YouTube in Firefox"
    echo "   • Make sure Firefox is completely closed"
    echo "   • Try running the Python script directly for more details:"
    echo "     python3 extract_cookies.py --list-profiles"
fi
