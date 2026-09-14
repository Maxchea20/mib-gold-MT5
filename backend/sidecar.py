"""Single process entry: FastAPI + optional built UI on one localhost port.

Tauri spawns this sidecar. You can also run it alone and open the printed URL.
No Mongo. No second frontend server.
"""
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    os.chdir(root)
    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
    except Exception:
        pass
    os.environ.setdefault("BROKER_MODE", "sim")
    os.environ.setdefault("HOST", "127.0.0.1")
    os.environ.setdefault("PORT", "8001")
    ui = root.parent / "frontend" / "build"
    if ui.is_dir():
        os.environ.setdefault("MIBGOLD_UI_DIR", str(ui))
    import uvicorn
    from server import app  # noqa: E402

    host = os.environ["HOST"]
    port = int(os.environ["PORT"])
    print(f"mib-gold engine on http://{host}:{port}  mode={os.environ.get('BROKER_MODE')}  (API /api  UI / if frontend/build exists)")
    uvicorn.run(app, host=host, port=port, log_level="info")
