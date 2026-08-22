@echo off
setlocal

cd /d "%~dp0"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo Starting GLP-1 AI Health Stack Watch...
echo Project folder: %CD%
echo.
echo Checking Python dependencies. Harmless pip cache warnings may appear on some systems.
echo.

python -m pip install --disable-pip-version-check --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency install failed. Please check your Python installation and try again.
    pause
    exit /b 1
)

echo.
echo Generating snapshot report in output\reports before launching the dashboard.
echo.

python generate_snapshot.py
if errorlevel 1 (
    echo.
    echo Snapshot report generation failed. The dashboard will still try to launch.
    echo Check the messages above for Yahoo Finance or RSS errors.
    echo.
)

echo.
echo Launching Streamlit. Close this window to stop the dashboard.
echo.
python -m streamlit run app.py

echo.
echo Dashboard stopped.
pause
