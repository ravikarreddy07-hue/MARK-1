@echo off
chcp 65001 > nul
title Push Quantum Binary Code to GitHub (MARK-1)
echo ======================================================================
echo   PUSHING QUANTUM BINARY TRADING TERMINAL TO GITHUB
echo   Target Repo: https://github.com/coder-pixel547/MARK-1.git
echo ======================================================================
echo.
echo Adding files and committing latest changes...
git add .
git commit -m "Quantum Binary TradingView Pro - Complete Codebase"

echo.
echo Pushing to GitHub (Branch: main)...
git push -u origin main

if %ERRORLEVEL% equ 0 (
    echo.
    echo ======================================================================
    echo [SUCCESS] Code successfully pushed to GitHub!
    echo View repository at: https://github.com/coder-pixel547/MARK-1
    echo ======================================================================
) else (
    echo.
    echo [NOTE] If prompted, sign in with your GitHub account in your browser,
    echo or use your GitHub Personal Access Token as the password.
)

echo.
pause
