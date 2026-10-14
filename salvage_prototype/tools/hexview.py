#!/usr/bin/env python3
"""Repository-level wrapper for the SALVAGE hex-view utility."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from salvage.tools.hexview import main
if __name__ == "__main__": raise SystemExit(main())
