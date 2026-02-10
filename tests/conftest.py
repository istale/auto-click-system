import sys
from pathlib import Path

# Ensure repo root is on sys.path so tests can import auto_click_core.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
