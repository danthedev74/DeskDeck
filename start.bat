@echo off
cd /d "%~dp0"
title DeskDeck
python agent.py %*
pause
