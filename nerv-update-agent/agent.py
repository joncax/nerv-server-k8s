import json
import os
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
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


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

    github_info = {}
    try:
        resp = requests.get(
            GITHUB_API.format(repo=cfg["github_repo"]),
            headers=github_headers(),
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            github_info = {
                "latest_version": data.get("tag_name", ""),
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
        "github": github_info,
    }


# ─── Update ───────────────────────────────────────────────────────────────────

@app.post("/apps/{app_name}/update")
def trigger_update(app_name: str):
    if app_name not in APPS:
        raise HTTPException(status_code=404, detail=f"App '{app_name}' not found")

    cfg = APPS[app_name]

    def event_stream():
        for line in update_app(
            app_name=app_name,
            image=cfg["image"],
            deployment=cfg["deployment"],
            namespace=cfg["namespace"],
        ):
            yield f"data: {line}\n\n"
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
