#!/bin/bash
# One-click launcher for Covered Call Scanner

echo "🚀 Starting Covered Call Scanner..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Found Python $PYTHON_VERSION"

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import streamlit" &> /dev/null; then
    echo "📥 Installing dependencies (this may take a minute)..."
    pip install -q -r requirements.txt
    echo "✓ Dependencies installed"
else
    echo "✓ Dependencies already installed"
fi

# Run the app
echo ""
echo "🌐 Starting Streamlit app..."
echo "The app will open in your browser at http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the app"
echo ""

streamlit run app.py
