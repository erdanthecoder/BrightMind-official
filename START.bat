@echo off
echo Installing requirements...
pip install flask flask-cors
echo.
echo Starting BrightMind Server...
python server.py
pause
