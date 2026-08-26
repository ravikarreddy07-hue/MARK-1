import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

if __name__ == "__main__":
    exit_code = pytest.main(["-v", "tests/test_indicator_app.py"])
    print(f"Pytest exited with code: {exit_code}")
    sys.exit(exit_code)
