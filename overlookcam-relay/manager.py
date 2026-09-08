from __future__ import annotations

import html
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from flask import Flask, redirect, render_template_string, request, url_for

from hosted_push import HostedPushClient


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("overlookcam-manager")

DATA_DIR = Path("/data")
CONFIG_PATH = DATA_DIR / "relay-config.json"
OPTIONS_PATH = DATA_DIR / "options.json"
PORT = 8099

app = Flask(__name__)
relay_lock = threading.Lock()
relay_process: subprocess.Popen[str] | None = None


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_")
    return value or "source"


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.is_file():
        try:
            payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("sources", []), list):
                return payload
        except Exception:
            LOGGER.exception("Unable to read %s", CONFIG_PATH)
    migrated = migrate_legacy_options()
    if migrated:
        save_config(migrated)
        return migrated
    return {"sources": []}


def migrate_legacy_options() -> dict[str, Any] | None:
    if not OPTIONS_PATH.is_file():
        return None
    try:
        options = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(options, dict):
        return None

    sources: list[dict[str, Any]] = []

    def add_source(prefix: str, default_name: str) -> None:
        host = str(options.get(f"{prefix}_mqtt_host", "") or "").strip()
        if not host:
            return
        sources.append({
            "id": f"source{len(sources) + 1}",
            "name": str(options.get(f"{prefix}_name", default_name) or default_name).strip(),
            "mqtt_host": host,
            "mqtt_port": int(options.get(f"{prefix}_mqtt_port", 1883) or 1883),
            "mqtt_user": str(options.get(f"{prefix}_mqtt_user", "") or ""),
            "mqtt_password": str(options.get(f"{prefix}_mqtt_password", "") or ""),
            "mqtt_topic": str(options.get(f"{prefix}_mqtt_topic", "frigate/events") or "frigate/events"),
            "push_cameras": str(options.get(f"{prefix}_push_cameras", "") or ""),
        })

    if "primary_mqtt_host" in options:
        add_source("primary", "Frigate")
        if bool(options.get("secondary_enabled", False)):
            add_source("secondary", "Frigate 2")
    elif "source_home_mqtt_host" in options:
        add_source("source_home", "Home")
        if bool(options.get("source_store_enabled", False)):
            add_source("source_store", "Store")

    return {"sources": sources} if sources else None


def save_config(config: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(CONFIG_PATH)


def build_relay_env(config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    sources = config.get("sources", [])
    source_ids: list[str] = []
    for source in sources:
        source_id = slugify(str(source.get("id", "")))
        prefix = "SOURCE_" + re.sub(r"[^A-Z0-9]", "_", source_id.upper())
        source_ids.append(source_id)
        env[f"{prefix}_ENABLED"] = "true"
        env[f"{prefix}_NAME"] = str(source.get("name", "Frigate") or "Frigate")
        env[f"{prefix}_MQTT_HOST"] = str(source.get("mqtt_host", ""))
        env[f"{prefix}_MQTT_PORT"] = str(source.get("mqtt_port", 1883))
        env[f"{prefix}_MQTT_USER"] = str(source.get("mqtt_user", ""))
        env[f"{prefix}_MQTT_PASSWORD"] = str(source.get("mqtt_password", ""))
        env[f"{prefix}_MQTT_TOPIC"] = str(source.get("mqtt_topic", "frigate/events") or "frigate/events")
        env[f"{prefix}_PUSH_CAMERAS"] = str(source.get("push_cameras", ""))
        env[f"{prefix}_SUPPRESS_DURING_SCHEDULE"] = "false"
    env["FRIGATE_SOURCES"] = ",".join(source_ids)
    return env


def stop_relay() -> None:
    global relay_process
    with relay_lock:
        proc = relay_process
        relay_process = None
        if proc is None or proc.poll() is not None:
            return
        LOGGER.info("Stopping relay process")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def start_relay() -> None:
    global relay_process
    config = load_config()
    sources = config.get("sources", [])
    if not sources:
        LOGGER.info("No Frigate sources configured yet; relay process will remain stopped")
        return
    for source in sources:
        if not str(source.get("mqtt_host", "")).strip():
            LOGGER.warning("Source %s has no MQTT host; relay process will remain stopped", source.get("name", "Frigate"))
            return
    with relay_lock:
        if relay_process is not None and relay_process.poll() is None:
            return
        LOGGER.info("Starting relay process for %s source%s", len(sources), "" if len(sources) == 1 else "s")
        relay_process = subprocess.Popen(
            [sys.executable, "relay.py"],
            cwd="/opt/overlookcam",
            env=build_relay_env(config),
            text=True,
        )


def restart_relay() -> None:
    stop_relay()
    start_relay()


def relay_status() -> str:
    with relay_lock:
        if relay_process is not None and relay_process.poll() is None:
            return "running"
    return "stopped"


def allocate_source_id(existing: set[str]) -> str:
    number = 1
    while f"source{number}" in existing:
        number += 1
    return f"source{number}"


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OverlookCam Relay</title>
<style>
:root { color-scheme: light dark; --bg:#f4f6f8; --card:#fff; --text:#1f2937; --muted:#667085; --border:#d0d5dd; --primary:#03a9f4; --danger:#b42318; --good:#067647; }
@media (prefers-color-scheme: dark) { :root { --bg:#111827; --card:#1f2937; --text:#f9fafb; --muted:#98a2b3; --border:#475467; } }
* { box-sizing:border-box; }
body { margin:0; font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }
.wrap { max-width:980px; margin:0 auto; padding:24px; }
h1 { margin:0 0 4px; font-size:28px; }
h2 { margin:0; font-size:20px; }
p { color:var(--muted); }
.header { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:20px; }
.status { font-weight:600; padding:7px 11px; border-radius:999px; background:rgba(6,118,71,.12); color:var(--good); }
.status.stopped { background:rgba(180,35,24,.12); color:var(--danger); }
.card { background:var(--card); border:1px solid var(--border); border-radius:14px; padding:20px; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
.source-head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:16px; }
.grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.full { grid-column:1/-1; }
label { display:block; font-size:13px; font-weight:600; margin-bottom:6px; }
input { width:100%; padding:11px 12px; border:1px solid var(--border); border-radius:8px; background:transparent; color:var(--text); font-size:15px; }
small { color:var(--muted); display:block; margin-top:5px; }
button { border:0; border-radius:8px; padding:10px 14px; font-size:14px; font-weight:700; cursor:pointer; }
.primary { background:var(--primary); color:white; }
.secondary { background:transparent; border:1px solid var(--border); color:var(--text); }
.danger { background:transparent; color:var(--danger); }
.actions { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:18px; }
.flash { border-radius:10px; padding:12px 14px; margin-bottom:16px; background:rgba(3,169,244,.12); }
.code { font-size:28px; letter-spacing:4px; font-weight:800; margin:8px 0; }
.empty { text-align:center; padding:34px 20px; }
@media (max-width:700px) { .grid { grid-template-columns:1fr; } .full { grid-column:auto; } .header { align-items:flex-start; flex-direction:column; } }
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div><h1>OverlookCam Relay</h1><p>Connect one or more Frigate installations to OverlookCam.</p></div>
    <div class="status {{ 'stopped' if status != 'running' else '' }}">Relay {{ status }}</div>
  </div>

  {% if message %}<div class="flash">{{ message }}</div>{% endif %}

  <form method="post" action="save" id="sources-form">
    <div id="sources">
      {% for source in sources %}
      <div class="card source-card">
        <input type="hidden" name="source_id" value="{{ source.id }}">
        <div class="source-head"><h2>{{ source.name or 'Frigate' }}</h2><button type="button" class="danger remove">Remove</button></div>
        <div class="grid">
          <div><label>Frigate server name</label><input name="name" value="{{ source.name }}" placeholder="Home, Office, Warehouse..." required></div>
          <div><label>MQTT host</label><input name="mqtt_host" value="{{ source.mqtt_host }}" placeholder="192.168.1.10 or mqtt.local" required></div>
          <div><label>MQTT port</label><input name="mqtt_port" type="number" min="1" max="65535" value="{{ source.mqtt_port or 1883 }}" required></div>
          <div><label>MQTT username</label><input name="mqtt_user" value="{{ source.mqtt_user }}" autocomplete="username"></div>
          <div><label>MQTT password</label><input name="mqtt_password" type="password" value="" placeholder="{{ 'Saved - leave blank to keep' if source.has_password else 'Optional' }}" autocomplete="current-password"></div>
          <div><label>Frigate MQTT topic</label><input name="mqtt_topic" value="{{ source.mqtt_topic or 'frigate/events' }}" required></div>
          <div class="full"><label>Camera filter</label><input name="push_cameras" value="{{ source.push_cameras }}" placeholder="Leave blank for all cameras"><small>Optional comma-separated Frigate camera IDs.</small></div>
        </div>
      </div>
      {% endfor %}
    </div>

    <div id="empty" class="card empty" style="display:{{ 'none' if sources else 'block' }}">
      <h2>No Frigate installations configured</h2>
      <p>Add your first Frigate server to begin receiving OverlookCam events.</p>
    </div>

    <div class="actions">
      <button type="button" id="add-source" class="secondary">+ Add Frigate installation</button>
      <button type="submit" class="primary">Save & restart relay</button>
    </div>
  </form>

  <div class="card" style="margin-top:22px">
    <h2>OverlookCam account</h2>
    <p>Pair this relay with the OverlookCam app or claim it from your OverlookCam account.</p>
    <div class="actions">
      <form method="post" action="pair"><button class="secondary" type="submit">Generate pairing code</button></form>
      <form method="post" action="claim"><button class="secondary" type="submit">Generate account claim code</button></form>
    </div>
    {% if code %}<div class="code">{{ code }}</div><small>Expires: {{ expires }}</small>{% endif %}
  </div>
</div>

<template id="source-template">
<div class="card source-card">
  <input type="hidden" name="source_id" value="">
  <div class="source-head"><h2>New Frigate installation</h2><button type="button" class="danger remove">Remove</button></div>
  <div class="grid">
    <div><label>Frigate server name</label><input name="name" placeholder="Home, Office, Warehouse..." required></div>
    <div><label>MQTT host</label><input name="mqtt_host" placeholder="192.168.1.10 or mqtt.local" required></div>
    <div><label>MQTT port</label><input name="mqtt_port" type="number" min="1" max="65535" value="1883" required></div>
    <div><label>MQTT username</label><input name="mqtt_user" autocomplete="username"></div>
    <div><label>MQTT password</label><input name="mqtt_password" type="password" placeholder="Optional" autocomplete="current-password"></div>
    <div><label>Frigate MQTT topic</label><input name="mqtt_topic" value="frigate/events" required></div>
    <div class="full"><label>Camera filter</label><input name="push_cameras" placeholder="Leave blank for all cameras"><small>Optional comma-separated Frigate camera IDs.</small></div>
  </div>
</div>
</template>
<script>
const sources = document.getElementById('sources');
const empty = document.getElementById('empty');
function refreshEmpty(){ empty.style.display = sources.querySelector('.source-card') ? 'none' : 'block'; }
document.getElementById('add-source').addEventListener('click', () => {
  sources.appendChild(document.getElementById('source-template').content.cloneNode(true));
  refreshEmpty();
});
document.addEventListener('click', e => {
  if (e.target.classList.contains('remove')) { e.target.closest('.source-card').remove(); refreshEmpty(); }
});
document.addEventListener('input', e => {
  if (e.target.name === 'name') { const card=e.target.closest('.source-card'); if(card) card.querySelector('h2').textContent=e.target.value || 'New Frigate installation'; }
});
</script>
</body>
</html>
"""


def view_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in config.get("sources", []):
        result.append({
            "id": str(source.get("id", "")),
            "name": html.escape(str(source.get("name", ""))),
            "mqtt_host": html.escape(str(source.get("mqtt_host", ""))),
            "mqtt_port": int(source.get("mqtt_port", 1883) or 1883),
            "mqtt_user": html.escape(str(source.get("mqtt_user", ""))),
            "mqtt_topic": html.escape(str(source.get("mqtt_topic", "frigate/events"))),
            "push_cameras": html.escape(str(source.get("push_cameras", ""))),
            "has_password": bool(source.get("mqtt_password", "")),
        })
    return result


def render(message: str = "", code: str = "", expires: str = ""):
    config = load_config()
    return render_template_string(
        PAGE,
        sources=view_sources(config),
        status=relay_status(),
        message=message,
        code=code,
        expires=expires,
    )


@app.get("/")
def index():
    return render()


@app.post("/save")
def save():
    old_config = load_config()
    old_by_id = {str(item.get("id", "")): item for item in old_config.get("sources", [])}
    ids = request.form.getlist("source_id")
    names = request.form.getlist("name")
    hosts = request.form.getlist("mqtt_host")
    ports = request.form.getlist("mqtt_port")
    users = request.form.getlist("mqtt_user")
    passwords = request.form.getlist("mqtt_password")
    topics = request.form.getlist("mqtt_topic")
    cameras = request.form.getlist("push_cameras")

    count = len(names)
    fields = [ids, hosts, ports, users, passwords, topics, cameras]
    if any(len(field) != count for field in fields):
        return render("The submitted Frigate configuration was incomplete."), 400

    existing_ids: set[str] = set()
    new_sources: list[dict[str, Any]] = []
    for i in range(count):
        source_id = slugify(ids[i]) if ids[i].strip() else allocate_source_id(existing_ids)
        while source_id in existing_ids:
            source_id = allocate_source_id(existing_ids)
        existing_ids.add(source_id)
        name = names[i].strip() or f"Frigate {i + 1}"
        host = hosts[i].strip()
        if not host:
            return render(f"MQTT host is required for {name}."), 400
        try:
            port = int(ports[i])
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            return render(f"MQTT port for {name} must be between 1 and 65535."), 400
        password = passwords[i]
        if not password and source_id in old_by_id:
            password = str(old_by_id[source_id].get("mqtt_password", ""))
        new_sources.append({
            "id": source_id,
            "name": name,
            "mqtt_host": host,
            "mqtt_port": port,
            "mqtt_user": users[i].strip(),
            "mqtt_password": password,
            "mqtt_topic": topics[i].strip() or "frigate/events",
            "push_cameras": cameras[i].strip(),
        })

    save_config({"sources": new_sources})
    restart_relay()
    return redirect("./?saved=1")


@app.post("/pair")
def pair():
    try:
        client = HostedPushClient()
        try:
            result = client.create_pairing_code()
        finally:
            client.close()
        return render("Enter this one-time code in the OverlookCam app.", result["pairing_code"], result["expires_at"])
    except Exception as exc:
        LOGGER.exception("Unable to create pairing code")
        return render(f"Unable to create pairing code: {exc}"), 502


@app.post("/claim")
def claim():
    try:
        client = HostedPushClient()
        try:
            result = client.create_claim_code()
        finally:
            client.close()
        return render("Enter this code at account.overlookcam.com to claim the relay.", result["claim_code"], result["expires_at"])
    except Exception as exc:
        LOGGER.exception("Unable to create claim code")
        return render(f"Unable to create claim code: {exc}"), 502


@app.get("/health")
def health():
    return {"ok": True, "relay": relay_status(), "sources": len(load_config().get("sources", []))}


def shutdown(signum: int, frame: Any) -> None:
    LOGGER.info("Received signal %s", signum)
    stop_relay()
    raise SystemExit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    start_relay()
    app.run(host="0.0.0.0", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
