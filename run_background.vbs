Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\reddy\.gemini\antigravity\scratch\binary-options-indicator"
WshShell.Run "python run.py", 0, False
Set WshShell = Nothing
