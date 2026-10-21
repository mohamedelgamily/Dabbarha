"""Run the durable notification scheduler as a separate supervised process."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import time

from app.core.config import SETTINGS
from app.core.notification_settings import NotificationSettings
from app.db.database import create_app_engine
from app.services.notification_worker import run_once
from app.services.push_provider import ExpoPushAdapter, MockPushAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Dabbarha payment reminder worker")
    parser.add_argument("--once", action="store_true", help="Run one scheduling/delivery cycle and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = NotificationSettings.from_environ(SETTINGS.app_env)
    if not settings.enabled:
        logging.info("notification_worker_disabled")
        return 0
    engine = create_app_engine(SETTINGS.database_url, pool_pre_ping=True)
    provider_name = os.environ.get("NOTIFICATION_PROVIDER", "expo")
    provider = MockPushAdapter() if provider_name == "mock" else ExpoPushAdapter(settings.expo_access_token)
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            try:
                counts = run_once(engine, settings, provider)
                logging.info("notification_worker_cycle scheduled=%d delivery_work=%d receipt_checks=%d",
                             counts["scheduled"], counts["deliveries"], counts["receipts"])
            except Exception as exc:
                # Log only exception class, never URLs, payloads, tokens or provider bodies.
                logging.error("notification_worker_cycle_failed error_type=%s", type(exc).__name__)
            if args.once or stopping:
                break
            time.sleep(settings.worker_poll_seconds)
    finally:
        provider.close()
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
