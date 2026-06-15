import json
import os
import sqlite3
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import requests

from apps_config import APPS
from update_runner import update_app, get_local_digest, write_log

app = FastAPI(title="nerv-update-agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LOG_FILE = "/var/log/nerv/magi-agent.log"
DB_PATH = "/opt/nerv-update-agent/versions.db"
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


# ─── SQLite helpers ───────────────────────────────────────────────────────────

def get_installed_version(app_name: str) -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT version, recorded_at, source FROM installed_versions WHERE app = ?",
            (app_name,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return {"version": row[0], "recorded_at": row[1], "source": row[2]}
        return {"version": None, "recorded_at": None, "source": None}
    except Exception:
        return {"version": None, "recorded_at": None, "source": None}


def save_installed_version(app_name: str, version: str, source: str = "update"):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO installed_versions (app, version, recorded_at, source)
            VALUES (?, ?, ?, ?)
        """, (app_name, version, datetime.now(timezone.utc).isoformat(), source))
        conn.commit()
        conn.close()
    except Exception as e:
        write_log(app_name, "save_version", "failed", {"error": str(e)})


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "agent": "magi"}


# ─── Apps ─────────────────────────────────────────────────────────────────────

@app.get("/apps")
def list_apps():
    return {"apps": list(APPS.keys())}


@app.get("/apps/{app_name}/info")
def app_info(app_name: str):
    if app_name not in APPS:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not found")

    cfg = APPS[app_name]
    local_digest = get_local_digest(cfg["image"])
    installed = get_installed_version(app_name)

    github_info = {}
    latest_version = None
    try:
        resp = requests.get(
            GITHUB_API.format(repo=cfg["github_repo"]),
            headers=github_headers(),
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            latest_version = data.get("tag_name", "")
            github_info = {
                "latest_version": latest_version,
                "release_url": data.get("html_url", ""),
                "published_at": data.get("published_at", ""),
            }
        elif resp.status_code == 403:
            github_info = {"error": "rate_limit"}
        else:
            github_info = {"error": f"http_{resp.status_code}"}
    except Exception:
        github_info = {"error": "github unreachable"}

    return {
        "name": app_name,
        "image": cfg["image"],
        "local_digest": local_digest,
        "installed_version": installed["version"],
        "installed_recorded_at": installed["recorded_at"],
        "github": github_info,
    }


# ─── Verify ───────────────────────────────────────────────────────────────────

@app.post("/apps/{app_name}/verify")
def verify_app(app_name: str):
    if app_name not in APPS:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not found")

    cfg = APPS[app_name]

    try:
        resp = requests.get(
            GITHUB_API.format(repo=cfg["github_repo"]),
            headers=github_headers(),
            timeout=5
        )
        if resp.status_code != 200:
            return {"status": "error", "detail": f"GitHub returned {resp.status_code}"}
        latest_version = resp.json().get("tag_name", "")
    except Exception:
        return {"status": "error", "detail": "GitHub unreachable"}

    save_installed_version(app_name, latest_version, source="verify")
    write_log(app_name, "verify", "success", {"version": latest_version})

    return {
        "status": "ok",
        "app": app_name,
        "version": latest_version,
        "source": "verify",
    }


# ─── Update ───────────────────────────────────────────────────────────────────

@app.post("/apps/{app_name}/update")
def trigger_update(app_name: str):
    if app_name not in APPS:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not found")

    cfg = APPS[app_name]

    latest_version = None
    try:
        resp = requests.get(
            GITHUB_API.format(repo=cfg["github_repo"]),
            headers=github_headers(),
            timeout=5
        )
        if resp.status_code == 200:
            latest_version = resp.json().get("tag_name", "")
    except Exception:
        pass

    def event_stream():
        for line in update_app(
            app_name=app_name,
            image=cfg["image"],
            deployment=cfg["deployment"],
            namespace=cfg["namespace"],
        ):
            yield f"data: {line}\n\n"
        if latest_version:
            save_installed_version(app_name, latest_version, source="update")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Logs ─────────────────────────────────────────────────────────────────────

@app.get("/logs")
def get_logs(app: str = None, limit: int = 50):
    if not os.path.exists(LOG_FILE):
        return {"logs": []}

    with open(LOG_FILE, "r") as f:
        lines = f.readlines()

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if app is None or entry.get("app") == app:
                entries.append(entry)
        except json.JSONDecodeError:
            continue

    entries.reverse()
    return {"logs": entries[:limit]}
