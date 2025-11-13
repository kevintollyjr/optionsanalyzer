# One-click launcher for Covered Call Scanner (Windows PowerShell)

Write-Host ""
Write-Host "🚀 Starting Covered Call Scanner..." -ForegroundColor Green
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Found $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python is not installed. Please install Python 3.10 or higher." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if virtual environment exists, create if not
if (-not (Test-Path "venv")) {
    Write-Host "📦 Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate virtual environment
Write-Host "🔧 Activating virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

# Check if dependencies are installed
try {
    python -c "import streamlit" 2>&1 | Out-Null
    Write-Host "✓ Dependencies already installed" -ForegroundColor Green
} catch {
    Write-Host "📥 Installing dependencies (this may take a minute)..." -ForegroundColor Yellow
    pip install -q -r requirements.txt
    Write-Host "✓ Dependencies installed" -ForegroundColor Green
}

# Run the app
Write-Host ""
Write-Host "🌐 Starting Streamlit app..." -ForegroundColor Green
Write-Host "The app will open in your browser at http://localhost:8501" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the app" -ForegroundColor Yellow
Write-Host ""

streamlit run app.py
