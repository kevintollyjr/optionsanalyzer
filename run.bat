@echo off
REM One-click launcher for Covered Call Scanner (Windows)

echo.
echo Starting Covered Call Scanner...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Please install Python 3.10 or higher.
    pause
    exit /b 1
)

echo Found Python
python --version

REM Check if virtual environment exists, create if not
if not exist "venv" (
    echo.
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Installing dependencies ^(this may take a minute^)...
    pip install -q -r requirements.txt
    echo Dependencies installed
) else (
    echo Dependencies already installed
)

REM Run the app
echo.
echo Starting Streamlit app...
echo The app will open in your browser at http://localhost:8501
echo.
echo Press Ctrl+C to stop the app
echo.

streamlit run app.py
