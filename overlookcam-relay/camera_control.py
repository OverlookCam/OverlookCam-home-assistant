from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from flask import Blueprint, jsonify, request

LOGGER = logging.getLogger("overlookcam-camera-control")
OPTIONS_PATH = Path("/data/options.json")

camera_control = Blueprint("camera_control", __name__)


def _load_options() -> dict[str, Any]:
    if not OPTIONS_PATH.is_file():
        return {}
    try:
        payload = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        LOGGER.exception("Unable to read %s", OPTIONS_PATH)
        return {}


def _control_config() -> dict[str, Any] | None:
    options = _load_options()
    camera = str(options.get("floodlight_camera", "") or "").strip()
    host = str(options.get("floodlight_host", "") or "").strip()
    username = str(options.get("floodlight_username", "") or "").strip()
    password = str(options.get("floodlight_password", "") or "")
    if not camera or not host or not username or not password:
        return None

    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"

    return {
        "camera": camera,
        "host": host.rstrip("/"),
        "username": username,
        "password": password,
        "verify_ssl": bool(options.get("floodlight_verify_ssl", False)),
    }


def _matches_camera(camera: str, config: dict[str, Any]) -> bool:
    return camera.strip().lower() == str(config["camera"]).strip().lower()


def _reolink_url(config: dict[str, Any], command: str) -> str:
    query = urlencode({
        "cmd": command,
        "user": config["username"],
        "password": config["password"],
    })
    return f"{config['host']}/cgi-bin/api.cgi?{query}"


def _reolink_request(config: dict[str, Any], command: str, body: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        with httpx.Client(verify=config["verify_ssl"], timeout=8.0) as client:
            response = client.post(
                _reolink_url(config, command),
                json=body,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        LOGGER.exception("Reolink %s request failed", command)
        raise RuntimeError(f"Reolink camera request failed: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise RuntimeError("Reolink camera returned an invalid response")
    result = payload[0]
    if not isinstance(result, dict):
        raise RuntimeError("Reolink camera returned an invalid response")
    if int(result.get("code", -1)) != 0:
        error = result.get("error") or result
        raise RuntimeError(f"Reolink camera rejected the request: {error}")
    return result


@camera_control.get("/api/cameras/<camera>/capabilities")
def capabilities(camera: str):
    config = _control_config()
    supported = bool(config and _matches_camera(camera, config))
    return jsonify({
        "camera": camera,
        "floodlight": supported,
    })


@camera_control.get("/api/cameras/<camera>/floodlight")
def floodlight_state(camera: str):
    config = _control_config()
    if not config or not _matches_camera(camera, config):
        return jsonify({"detail": "Floodlight control is not configured for this camera."}), 404

    try:
        result = _reolink_request(
            config,
            "GetWhiteLed",
            [{"cmd": "GetWhiteLed", "action": 0, "param": {"channel": 0}}],
        )
        white_led = ((result.get("value") or {}).get("WhiteLed") or {})
        return jsonify({
            "camera": camera,
            "on": int(white_led.get("state", 0)) == 1,
            "brightness": int(white_led.get("bright", 100) or 100),
        })
    except RuntimeError as exc:
        return jsonify({"detail": str(exc)}), 502


@camera_control.post("/api/cameras/<camera>/floodlight")
def set_floodlight(camera: str):
    config = _control_config()
    if not config or not _matches_camera(camera, config):
        return jsonify({"detail": "Floodlight control is not configured for this camera."}), 404

    payload = request.get_json(silent=True) or {}
    if "on" not in payload or not isinstance(payload["on"], bool):
        return jsonify({"detail": "Request body must contain boolean field 'on'."}), 400

    brightness = payload.get("brightness", 100)
    try:
        brightness = max(1, min(100, int(brightness)))
    except (TypeError, ValueError):
        return jsonify({"detail": "Brightness must be an integer from 1 to 100."}), 400

    try:
        _reolink_request(
            config,
            "SetWhiteLed",
            [{
                "cmd": "SetWhiteLed",
                "action": 0,
                "param": {
                    "WhiteLed": {
                        "channel": 0,
                        "mode": 0,
                        "state": 1 if payload["on"] else 0,
                        "bright": brightness,
                    }
                },
            }],
        )
        return jsonify({
            "camera": camera,
            "on": payload["on"],
            "brightness": brightness,
        })
    except RuntimeError as exc:
        return jsonify({"detail": str(exc)}), 502
