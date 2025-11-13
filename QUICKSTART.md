# Quick Start Guide

## 🚀 Easiest Ways to Run This App

### Option 1: One-Click Launcher (Recommended for Beginners)

#### Mac/Linux:
```bash
cd optionsanalyzer
chmod +x run.sh
./run.sh
```

#### Windows (Command Prompt):
```cmd
cd optionsanalyzer
run.bat
```

#### Windows (PowerShell):
```powershell
cd optionsanalyzer
.\run.ps1
```

**That's it!** The script will:
- ✅ Check for Python
- ✅ Create a virtual environment
- ✅ Install all dependencies
- ✅ Launch the app in your browser

---

### Option 2: Docker (One Command)

If you have Docker installed:

```bash
cd optionsanalyzer
docker-compose up
```

Then open your browser to: **http://localhost:8501**

To stop: `Ctrl+C` then `docker-compose down`

---

### Option 3: Manual Installation (Traditional Way)

```bash
cd optionsanalyzer
pip install -r requirements.txt
streamlit run app.py
```

---

### Option 4: Deploy to Streamlit Cloud (Free Web App)

1. Push this repository to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Sign in with GitHub
4. Click "New app"
5. Select your repository and branch
6. Set main file path: `app.py`
7. Click "Deploy"

Your app will be live at a public URL like: `https://your-app.streamlit.app`

**Benefits:**
- ✅ No local installation needed
- ✅ Access from any device
- ✅ Share with others via URL
- ✅ Automatically updates when you push to GitHub

---

## 🎯 After Launch

Once the app is running, you'll see:

1. **Sidebar** (left) - Configure your scan:
   - Enter tickers: `AAPL, MSFT, JPM`
   - Set delta range: `0.15` to `0.30`
   - Set DTE range: `5` to `90` days
   - Enable filters (OTM, open interest, spread)

2. **Main Area** - Click "Run Scan" and view:
   - Current prices and volatility metrics
   - Top opportunities by IV richness
   - Top opportunities by annualized yield
   - Interactive charts
   - Full sortable data tables

---

## 📋 Requirements

- Python 3.10 or higher
- Internet connection (for fetching market data)

---

## 🆘 Troubleshooting

### "Python not found"
Install Python from [python.org](https://www.python.org/downloads/)

### "Permission denied" on Mac/Linux
Run: `chmod +x run.sh` first

### "Execution policy" error on Windows PowerShell
Run PowerShell as Administrator and execute:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Port 8501 already in use
Another Streamlit app is running. Stop it or use a different port:
```bash
streamlit run app.py --server.port 8502
```

### Dependencies fail to install
Try upgrading pip first:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🎉 You're Ready!

Try scanning some tickers like:
- **Blue chips**: `JPM, BAC, WFC, GS`
- **Tech**: `AAPL, MSFT, GOOGL, META`
- **Dividend stocks**: `MO, T, VZ, PFE`
- **High IV stocks**: `TSLA, NVDA, AMD, PLTR`

Experiment with different delta ranges and DTE windows to find covered call opportunities that match your strategy!
