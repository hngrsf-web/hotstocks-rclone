import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

APP_VERSION = "1.0.0-cloud"
CLOUD_USER = os.getenv("CLOUD_USER", "trading")
CLOUD_PASSWORD = os.getenv("CLOUD_PASSWORD", "")
INGEST_TOKEN = os.getenv("INGEST_TOKEN", "")
STALE_MINUTES = int(os.getenv("STALE_MINUTES", "10"))
SNAPSHOT_PATH = Path(os.getenv("SNAPSHOT_PATH", "/tmp/hot_stocks_live.json"))
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="UGREEN Trading Control Cloud", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def iso_now() -> str:
    return utcnow().isoformat()

def load_snapshot() -> dict[str, Any] | None:
    try:
        if not SNAPSHOT_PATH.exists():
            return None
        raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None

def source_time(s: dict[str, Any] | None) -> datetime | None:
    if not s:
        return None
    value = s.get("generated_at_utc")
    if not value:
        value = (((s.get("endpoints") or {}).get("health") or {}).get("data") or {}).get("server_time")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None

def cloud_meta(s: dict[str, Any] | None) -> dict[str, Any]:
    t = source_time(s)
    age = None
    if t:
        age = max(0, int((utcnow() - t.astimezone(timezone.utc)).total_seconds()))
    return {
        "cloud_version": APP_VERSION,
        "source_generated_at": t.isoformat() if t else None,
        "age_seconds": age,
        "stale": age is None or age > STALE_MINUTES * 60,
        "stale_after_minutes": STALE_MINUTES,
        "read_only": True,
        "orders_enabled": False,
    }

def basic_ok(request: Request) -> bool:
    if not CLOUD_PASSWORD:
        return False
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        return False
    try:
        import base64
        decoded = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
        user, password = decoded.split(":", 1)
        return secrets.compare_digest(user, CLOUD_USER) and secrets.compare_digest(password, CLOUD_PASSWORD)
    except Exception:
        return False

@app.middleware("http")
async def protect_dashboard(request: Request, call_next):
    p = request.url.path
    if p in {"/health", "/api/ingest"}:
        return await call_next(request)
    if not basic_ok(request):
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="UGREEN Trading Control Cloud"'},
            content="Authentication required",
        )
    response = await call_next(request)
    if p == "/" or p.startswith("/static/") or p.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response

@app.get("/health")
def health():
    s = load_snapshot()
    return {
        "ok": True,
        "app": "UGREEN Trading Control Cloud",
        "version": APP_VERSION,
        "snapshot_present": bool(s),
        **cloud_meta(s),
    }

@app.post("/api/ingest")
async def ingest(request: Request, authorization: str | None = Header(default=None)):
    if not INGEST_TOKEN:
        raise HTTPException(status_code=503, detail="ingest token not configured")
    expected = f"Bearer {INGEST_TOKEN}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="invalid ingest token")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="json root must be an object")
    if not isinstance(payload.get("endpoints"), dict):
        raise HTTPException(status_code=400, detail="missing endpoints")
    tmp = SNAPSHOT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SNAPSHOT_PATH)
    return {"ok": True, "received_at": iso_now(), "generated_at_utc": payload.get("generated_at_utc")}

@app.get("/api/snapshot")
def snapshot():
    s = load_snapshot()
    if not s:
        return JSONResponse({"ok": False, "snapshot": None, "cloud": cloud_meta(None)}, status_code=200)
    return {"ok": True, "snapshot": s, "cloud": cloud_meta(s)}

@app.get("/", response_class=HTMLResponse)
def root():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")
