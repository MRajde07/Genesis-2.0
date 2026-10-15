#!/usr/bin/env python3
"""Repository-level wrapper for the SALVAGE probe utility."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from salvage.tools.probe import main
if __name__ == "__main__": raise SystemExit(main())
