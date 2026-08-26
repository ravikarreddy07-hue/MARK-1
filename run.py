import uvicorn
import os
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("QUANTUM BINARY OPTIONS INDICATOR TERMINAL")
    print(f"Server running on: http://localhost:{port} or http://127.0.0.1:{port}")
    print("=" * 60)
    
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
