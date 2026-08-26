import os
import subprocess

target_dir = r"C:\Users\reddy\.gemini\antigravity\scratch\binary-options-indicator"
vbs_script = os.path.join(target_dir, "run_background.vbs")
appdata = os.environ.get("APPDATA", "")
startup_dir = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
shortcut_path = os.path.join(startup_dir, "QuantumBinaryIndicator.bat")

# Create a clean startup batch file in the startup folder
with open(shortcut_path, "w", encoding="utf-8") as f:
    f.write(f'@echo off\nwscript.exe "{vbs_script}"\n')

print(f"SUCCESS: Configured Windows Startup launcher at {shortcut_path}")
