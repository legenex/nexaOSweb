"""Scheduled classification retry sweep.

Opt in through NEXA classify_sweep_enabled. When enabled, a background asyncio task wakes
on the configured interval and runs the sweep in a worker thread so the blocking model
calls do not stall the event loop. Disabled by default so tests and fresh checkouts do
not spawn it.
"""

import asyncio
import logging

from fastapi import FastAPI

from app.agents.classify import run_retry_sweep
from app.db import SessionLocal
from app.settings import get_settings

logger = logging.getLogger(__name__)


def _sweep_once() -> int:
    db = SessionLocal()
    try:
        return run_retry_sweep(db, batch=get_settings().classify_batch)
    finally:
        db.close()


async def _sweep_loop() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.classify_sweep_interval)
        try:
            processed = await asyncio.to_thread(_sweep_once)
            if processed:
                logger.info("classify sweep processed %s items", processed)
        except Exception:  # noqa: BLE001
            logger.exception("classify sweep iteration failed")


def register_scheduler(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _start_sweep() -> None:
        if not get_settings().classify_sweep_enabled:
            return
        app.state.sweep_task = asyncio.create_task(_sweep_loop())

    @app.on_event("shutdown")
    async def _stop_sweep() -> None:
        task = getattr(app.state, "sweep_task", None)
        if task is not None:
            task.cancel()
