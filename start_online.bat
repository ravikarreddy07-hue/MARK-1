@echo off
chcp 65001 > nul
title Quantum Binary - Online Launcher
echo ========================================================
echo   QUANTUM BINARY - STARTING ONLINE HTTPS SERVER
echo ========================================================
echo.
echo 1. Starting local indicator backend...
start /B python run.py
timeout /t 2 > nul
echo.
echo 2. Launching Cloudflare secure online tunnel...
cloudflared.exe tunnel --url http://localhost:5000
pause
