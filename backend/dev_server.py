"""Local end-to-end preview: the API over the fictional test fixtures, plus the built UI.

    cd ui-v2 && npm run build          # → ui-v2/out
    cd backend && python dev_server.py  # → http://localhost:8000   (DEV_WRITES=1 to allow writes)

Every fixture user's password is "1234". Nothing here touches the real Sheet.
"""
import hashlib
import os
import sys

import uvicorn
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "tests")]

from api.config import Settings  # noqa: E402
from api.main import create_app  # noqa: E402
from fixtures import build  # noqa: E402
from geri_core import MemoryStore  # noqa: E402

frames = build()
frames["staff"]["password"] = hashlib.sha256(b"1234").hexdigest()
store = MemoryStore(frames)
app = create_app(Settings(session_secret="dev" * 12, read_only=os.environ.get("DEV_WRITES") != "1",
                          cookie_secure=False), store_factory=lambda: store)
ui = os.path.join(HERE, "..", "ui-v2", "out")
if os.path.isdir(ui):
    app.mount("/", StaticFiles(directory=ui, html=True), name="ui")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
