import sqlite3
import requests
import json
from datetime import datetime, timezone

DB_PATH = "/opt/nerv-update-agent/versions.db"
BASE_URL = "http://192.168.1.50"
NOW = datetime.now(timezone.utc).isoformat()

apps = [
    {
        "app": "sonarr",
        "url": f"{BASE_URL}:30989/api/v3/system/status",
        "headers": {"X-Api-Key": "688f45f679ce490683f76e91b8b1cb84"},
        "field": "version",
        "prefix": "v"
    },
    {
        "app": "radarr",
        "url": f"{BASE_URL}:30878/api/v3/system/status",
        "headers": {"X-Api-Key": "13b0ffd51bfa4fec86073088e016f715"},
        "field": "version",
        "prefix": "v"
    },
    {
        "app": "bazarr",
        "url": f"{BASE_URL}:30767/api/system/status",
        "headers": {"X-Api-Key": "f1d50378719f9df7b71d6345dae1bd30"},
        "field": "bazarr_version",
        "nested": "data",
        "prefix": "v"
    },
    {
        "app": "prowlarr",
        "url": f"{BASE_URL}:30696/api/v1/system/status",
        "headers": {"X-Api-Key": "f96ecbdac8834ca9b888643ab3653d34"},
        "field": "version",
        "prefix": "v"
    },
    {
        "app": "jellyfin",
        "url": f"{BASE_URL}:30096/System/Info/Public",
        "headers": {},
        "field": "Version",
        "prefix": "v"
    },
]

def get_transmission_version():
    try:
        r1 = requests.get(f"{BASE_URL}:30091/transmission/rpc", timeout=5)
        session_id = r1.headers.get("X-Transmission-Session-Id", "")
        r2 = requests.post(
            f"{BASE_URL}:30091/transmission/rpc",
            headers={"X-Transmission-Session-Id": session_id, "Content-Type": "application/json"},
            json={"method": "session-get", "arguments": {"fields": ["version"]}},
            timeout=5
        )
        version = r2.json()["arguments"]["version"].split(" ")[0]
        return version
    except Exception as e:
        print(f"  transmission: error — {e}")
        return None

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS installed_versions (
        app TEXT PRIMARY KEY,
        version TEXT,
        recorded_at TEXT,
        source TEXT
    )
""")
conn.commit()

print("Bootstrap — registar versões instaladas")
print("=" * 45)

for cfg in apps:
    try:
        r = requests.get(cfg["url"], headers=cfg["headers"], timeout=5)
        data = r.json()
        if "nested" in cfg:
            data = data[cfg["nested"]]
        raw_version = data[cfg["field"]]
        prefix = cfg.get("prefix", "")
        version = f"{prefix}{raw_version}" if not raw_version.startswith(prefix) else raw_version
        cur.execute("""
            INSERT OR REPLACE INTO installed_versions (app, version, recorded_at, source)
            VALUES (?, ?, ?, ?)
        """, (cfg["app"], version, NOW, "bootstrap"))
        conn.commit()
        print(f"  {cfg['app']:15} {version}")
    except Exception as e:
        print(f"  {cfg['app']:15} error — {e}")

# Transmission — lógica especial
tr_version = get_transmission_version()
if tr_version:
    cur.execute("""
        INSERT OR REPLACE INTO installed_versions (app, version, recorded_at, source)
        VALUES (?, ?, ?, ?)
    """, ("transmission", tr_version, NOW, "bootstrap"))
    conn.commit()
    print(f"  {'transmission':15} {tr_version}")

# Filebrowser — sem API
cur.execute("""
    INSERT OR REPLACE INTO installed_versions (app, version, recorded_at, source)
    VALUES (?, ?, ?, ?)
""", ("filebrowser", None, NOW, "bootstrap"))
conn.commit()
print(f"  {'filebrowser':15} unknown (no API)")

conn.close()
print("=" * 45)
print("Done. Verifying...")
print()

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute("SELECT app, version, source, recorded_at FROM installed_versions ORDER BY app")
rows = cur.fetchall()
conn.close()

print(f"{'App':15} {'Version':20} {'Source':10} Recorded at")
print("-" * 65)
for row in rows:
    version = row[1] if row[1] else "unknown"
    print(f"  {row[0]:13} {version:20} {row[2]:10} {row[3]}")
