@echo off
cd /d "%~dp0"
echo Installing DeskDeck requirements...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Done. Now run start.bat
pause
