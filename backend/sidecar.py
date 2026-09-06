"""Sidecar entrypoint for the Tauri build. PyInstaller bundles this into binaries/mibgold-backend-<triple>.exe.

Build (Windows, inside /app/backend):
    pip install pyinstaller MetaTrader5
    pyinstaller --onefile --name mibgold-backend-x86_64-pc-windows-msvc sidecar.py
    move dist\\mibgold-backend-x86_64-pc-windows-msvc.exe ..\\desktop\\src-tauri\\binaries\\
"""
import os
import sys
import uvicorn

if __name__ == "__main__":
    os.environ.setdefault("BROKER_MODE", "mt5")
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "mibgold")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from server import app  # noqa: E402
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8001")), log_level="info")
