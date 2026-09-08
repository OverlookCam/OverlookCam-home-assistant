from __future__ import annotations

import signal
from typing import Any

from waitress import serve

from manager import PORT, app, start_relay, stop_relay


def shutdown(signum: int, frame: Any) -> None:
    stop_relay()
    raise SystemExit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    start_relay()
    serve(app, host="0.0.0.0", port=PORT, threads=4)


if __name__ == "__main__":
    main()
