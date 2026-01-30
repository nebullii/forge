#!/bin/bash
# Forge Setup

set -e

echo "Forge Setup"
echo "==========="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 required. Install from https://python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python $PYTHON_VERSION"

# Create venv
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install
echo "Installing forge..."
pip install -e . --quiet

echo ""
echo "Done! Run: source venv/bin/activate"
echo ""
echo "Then: forge new my-project"
