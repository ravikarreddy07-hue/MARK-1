@echo off
chcp 65001 > nul
echo ======================================================================
echo   QUANTUM BINARY - INSTALL AUTO-START ON WINDOWS BOOT
echo ======================================================================
echo.
echo Installing background auto-startup shortcut into Windows Startup folder...

set TARGET_DIR=%~dp0
set VBS_SCRIPT=%TARGET_DIR%run_background.vbs
set STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_FOLDER%\QuantumBinaryIndicator.lnk

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%VBS_SCRIPT%\"'; $s.WorkingDirectory = '%TARGET_DIR%'; $s.Save()"

echo.
echo [SUCCESS] Auto-start configured!
echo The terminal will now automatically start in the background whenever your PC boots.
echo You can access it anytime at: http://localhost:5000
echo.
pause
