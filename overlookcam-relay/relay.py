from __future__ import annotations

import json
import logging
import os
import queue
import re
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime, time as clock_time, timezone
from typing import Any
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt

from hosted_push import HostedPushClient


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("overlookcam-relay")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def display_name(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


def csv_set(name: str, default: str = "") -> set[str]:
    raw = os.getenv(name, default)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def parse_clock(name: str, default: str) -> clock_time:
    raw = os.getenv(name, default).strip()
    try:
        hour_text, minute_text = raw.split(":", 1)
        return clock_time(hour=int(hour_text), minute=int(minute_text))
    except Exception as exc:
        raise RuntimeError(f"{name} must use HH:MM format") from exc


def normalize_source_id(value: str) -> str:
    source_id = value.strip().lower()
    if not source_id:
        raise RuntimeError("FRIGATE_SOURCES contains an empty source id")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", source_id):
        raise RuntimeError(f"Invalid Frigate source id {value!r}; use letters, numbers, underscores, and hyphens")
    return source_id


def env_prefix(source_id: str) -> str:
    return "SOURCE_" + re.sub(r"[^A-Z0-9]", "_", source_id.upper())


@dataclass(frozen=True)
class SourceConfig:
    source_id: str
    env_prefix: str
    name: str
    host: str
    port: int
    username: str | None
    password: str | None
    topic: str
    camera_filter: set[str]
    suppress_during_schedule: bool
    timezone: ZoneInfo
    weekday_open: clock_time
    weekday_close: clock_time
    saturday_open: clock_time
    saturday_close: clock_time

    @classmethod
    def from_source_id(cls, source_id: str) -> "SourceConfig | None":
        source_id = normalize_source_id(source_id)
        prefix = env_prefix(source_id)
        if not env_bool(f"{prefix}_ENABLED", True):
            return None
        host = os.getenv(f"{prefix}_MQTT_HOST", "").strip()
        if not host:
            raise RuntimeError(f"{prefix}_MQTT_HOST is required for enabled source {source_id}")
        name = os.getenv(f"{prefix}_NAME", display_name(source_id)).strip() or display_name(source_id)
        topic = os.getenv(f"{prefix}_MQTT_TOPIC", os.getenv("MQTT_TOPIC", "frigate/events")).strip() or "frigate/events"
        timezone_name = os.getenv(f"{prefix}_TIMEZONE", "UTC").strip() or "UTC"
        return cls(
            source_id=source_id,
            env_prefix=prefix,
            name=name,
            host=host,
            port=int(os.getenv(f"{prefix}_MQTT_PORT", "1883")),
            username=os.getenv(f"{prefix}_MQTT_USER", "").strip() or None,
            password=os.getenv(f"{prefix}_MQTT_PASSWORD", "") or None,
            topic=topic,
            camera_filter=csv_set(f"{prefix}_PUSH_CAMERAS"),
            suppress_during_schedule=env_bool(f"{prefix}_SUPPRESS_DURING_SCHEDULE", False),
            timezone=ZoneInfo(timezone_name),
            weekday_open=parse_clock(f"{prefix}_WEEKDAY_OPEN", "09:00"),
            weekday_close=parse_clock(f"{prefix}_WEEKDAY_CLOSE", "17:00"),
            saturday_open=parse_clock(f"{prefix}_SATURDAY_OPEN", "09:00"),
            saturday_close=parse_clock(f"{prefix}_SATURDAY_CLOSE", "12:00"),
        )

    def schedule_is_active(self) -> bool:
        if not self.suppress_during_schedule:
            return False
        now = datetime.now(self.timezone)
        local_time = now.time().replace(tzinfo=None)
        if now.weekday() <= 4:
            return self.weekday_open <= local_time < self.weekday_close
        if now.weekday() == 5:
            return self.saturday_open <= local_time < self.saturday_close
        return False


@dataclass(frozen=True)
class FrigateNotification:
    source_id: str
    source_name: str
    event_id: str
    camera: str
    label: str
    event_type: str
    timestamp: datetime

    @property
    def unique_id(self) -> str:
        return f"{self.source_id}:{self.event_id}"

    def push_payload(self) -> dict[str, str]:
        return {
            "server_id": self.source_id,
            "server_name": self.source_name,
            "camera_id": self.camera,
            "camera_name": display_name(self.camera),
            "event_id": self.event_id,
            "label": self.label,
            "event_type": self.event_type,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        }


class FrigatePushRelay:
    def __init__(self) -> None:
        self.labels = csv_set("PUSH_LABELS", "person")
        self.event_types = csv_set("PUSH_EVENT_TYPES", "new")
        source_ids = [normalize_source_id(value) for value in os.getenv("FRIGATE_SOURCES", "").split(",") if value.strip()]
        if not source_ids:
            raise RuntimeError("FRIGATE_SOURCES must list at least one Frigate source id")
        if len(source_ids) != len(set(source_ids)):
            raise RuntimeError("FRIGATE_SOURCES contains duplicate source ids")
        self.sources = [source for source_id in source_ids if (source := SourceConfig.from_source_id(source_id)) is not None]
        if not self.sources:
            raise RuntimeError("At least one Frigate source must be enabled")

        self.push = HostedPushClient()
        self.notifications: queue.Queue[FrigateNotification] = queue.Queue(maxsize=1000)
        self.stop_event = threading.Event()
        self.clients: list[mqtt.Client] = []
        self.pending: set[str] = set()
        self.seen: dict[str, float] = {}
        self.state_lock = threading.Lock()
        self.worker = threading.Thread(target=self._worker_loop, name="push-worker", daemon=True)

    def start(self) -> None:
        LOGGER.info(
            "Starting OverlookCam Relay for %s; labels=%s event_types=%s installation=%s",
            ", ".join(source.name for source in self.sources),
            ",".join(sorted(self.labels)) or "all",
            ",".join(sorted(self.event_types)),
            self.push.credentials.installation_id,
        )
        inventory = [{"source_id": source.source_id, "display_name": source.name} for source in self.sources]
        if self.push.publish_sources(inventory):
            LOGGER.info("Published %s Frigate source%s to Push Service", len(inventory), "" if len(inventory) == 1 else "s")

        for source in self.sources:
            if source.camera_filter:
                LOGGER.info("%s camera filter: %s", source.name, ",".join(sorted(source.camera_filter)))
            if source.suppress_during_schedule:
                LOGGER.info(
                    "%s schedule suppression enabled: Mon-Fri %s-%s, Sat %s-%s, timezone=%s",
                    source.name,
                    source.weekday_open.strftime("%H:%M"),
                    source.weekday_close.strftime("%H:%M"),
                    source.saturday_open.strftime("%H:%M"),
                    source.saturday_close.strftime("%H:%M"),
                    source.timezone.key,
                )

        self.worker.start()
        for source in self.sources:
            client = self._build_mqtt_client(source)
            self.clients.append(client)
            client.connect_async(source.host, source.port, keepalive=60)
            client.loop_start()
        while not self.stop_event.wait(1.0):
            self._purge_seen()

    def stop(self) -> None:
        if self.stop_event.is_set():
            return
        LOGGER.info("Stopping OverlookCam Relay")
        self.stop_event.set()
        for client in self.clients:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                LOGGER.exception("Error while stopping MQTT client")
        self.worker.join(timeout=10)
        self.push.close()

    def _build_mqtt_client(self, source: SourceConfig) -> mqtt.Client:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"overlookcam-relay-{source.source_id}"[:23], clean_session=True)
        if source.username:
            client.username_pw_set(source.username, source.password)
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.user_data_set(source)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        return client

    def _on_connect(self, client: mqtt.Client, userdata: SourceConfig, flags: mqtt.ConnectFlags, reason_code: mqtt.ReasonCode, properties: mqtt.Properties | None) -> None:
        if reason_code.is_failure:
            LOGGER.error("%s MQTT connection failed to %s:%s: %s", userdata.name, userdata.host, userdata.port, reason_code)
            return
        LOGGER.info("%s MQTT connected to %s:%s; subscribing to %s", userdata.name, userdata.host, userdata.port, userdata.topic)
        client.subscribe(userdata.topic, qos=0)

    def _on_disconnect(self, client: mqtt.Client, userdata: SourceConfig, disconnect_flags: mqtt.DisconnectFlags, reason_code: mqtt.ReasonCode, properties: mqtt.Properties | None) -> None:
        if self.stop_event.is_set():
            return
        LOGGER.warning("%s MQTT disconnected: %s; reconnecting automatically", userdata.name, reason_code)

    def _source_allows(self, source: SourceConfig, camera: str) -> bool:
        if source.camera_filter and camera.lower() not in source.camera_filter:
            LOGGER.debug("Suppressing %s event from filtered camera %s", source.name, camera)
            return False
        if source.schedule_is_active():
            LOGGER.debug("Suppressing %s event during configured schedule from %s", source.name, camera)
            return False
        return True

    def _on_message(self, client: mqtt.Client, userdata: SourceConfig, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except Exception:
            LOGGER.exception("%s MQTT payload was not valid JSON", userdata.name)
            return
        event_type = str(payload.get("type", "")).lower()
        if event_type not in self.event_types:
            return
        event = payload.get("after") or payload.get("before") or {}
        if not isinstance(event, dict):
            return
        event_id = str(event.get("id", "")).strip()
        camera = str(event.get("camera", "")).strip()
        label = str(event.get("label", "")).strip().lower()
        false_positive = bool(event.get("false_positive", False))
        if not event_id or not camera or not label or false_positive:
            return
        if self.labels and label not in self.labels:
            return
        if not self._source_allows(userdata, camera):
            return
        event_timestamp = event.get("start_time") or event.get("end_time")
        try:
            timestamp = datetime.fromtimestamp(float(event_timestamp), tz=timezone.utc) if event_timestamp is not None else datetime.now(timezone.utc)
        except (TypeError, ValueError, OSError):
            timestamp = datetime.now(timezone.utc)

        notification = FrigateNotification(userdata.source_id, userdata.name, event_id, camera, label, event_type, timestamp)
        with self.state_lock:
            if notification.unique_id in self.pending or notification.unique_id in self.seen:
                return
            self.pending.add(notification.unique_id)
        try:
            self.notifications.put_nowait(notification)
        except queue.Full:
            LOGGER.error("Notification queue is full; dropping event %s", notification.unique_id)
            with self.state_lock:
                self.pending.discard(notification.unique_id)

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set() or not self.notifications.empty():
            try:
                notification = self.notifications.get(timeout=1.0)
            except queue.Empty:
                continue
            accepted, devices, delivered, failed = self.push.submit_event(notification.push_payload())
            with self.state_lock:
                self.pending.discard(notification.unique_id)
                if accepted:
                    self.seen[notification.unique_id] = time.time()
            if accepted:
                LOGGER.info("Push Service accepted %s event %s on %s; devices=%s delivered=%s failed=%s", notification.source_name, notification.event_id, notification.camera, devices, delivered, failed)
            else:
                LOGGER.error("Push Service did not accept %s event %s", notification.source_name, notification.event_id)
            self.notifications.task_done()

    def _purge_seen(self) -> None:
        cutoff = time.time() - 12 * 60 * 60
        with self.state_lock:
            expired = [unique_id for unique_id, seen_at in self.seen.items() if seen_at < cutoff]
            for unique_id in expired:
                del self.seen[unique_id]


def main() -> None:
    relay = FrigatePushRelay()

    def handle_signal(signum: int, frame: Any) -> None:
        LOGGER.info("Received signal %s", signum)
        relay.stop()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    try:
        relay.start()
    finally:
        relay.stop()


if __name__ == "__main__":
    main()
