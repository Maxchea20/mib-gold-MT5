#!/usr/bin/env python3
"""One command: engine + UI on http://127.0.0.1:8001

    python run_app.py
"""
import runpy
from pathlib import Path

sidecar = Path(__file__).resolve().parent / "backend" / "sidecar.py"
runpy.run_path(str(sidecar), run_name="__main__")
