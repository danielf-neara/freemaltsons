#!/bin/bash
# Freemaltson's Whisky Nights - start the app

cd "$(dirname "$0")"

# Install dependencies if needed
pip3 install flask requests beautifulsoup4 -q 2>/dev/null

# Set PYTHONPATH to find pip3-installed packages
SITE=$(python3 -c "import site; print(site.getusersitepackages())" 2>/dev/null || echo "")
if [ -n "$SITE" ]; then
  export PYTHONPATH="$SITE:$PYTHONPATH"
fi

echo ""
echo "  Freemaltson's Whisky Nights"
echo "  Opening at http://localhost:5001"
echo "  Press Ctrl+C to stop"
echo ""

# Open browser after short delay
(sleep 1 && open http://localhost:5001) &

python3 app.py
