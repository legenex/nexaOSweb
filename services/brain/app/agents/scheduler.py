"""Scheduled background jobs: the classification retry sweep and the nightly Dreaming run.

Each is opt in through a NEXA setting. When enabled, a background asyncio task wakes on the
configured interval and runs the work in a worker thread so the blocking model calls do not
stall the event loop. Both are disabled by default so tests and fresh checkouts do not spawn
them. The manual /dreaming/run trigger works regardless of the schedule.
"""

import asyncio
import logging

from fastapi import FastAPI

from app.agents.classify import run_retry_sweep
from app.agents.dreaming import run_dream
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


def _dream_once() -> int:
    db = SessionLocal()
    try:
        run = run_dream(db, trigger="scheduled")
        return run.candidates_created
    finally:
        db.close()


async def _dream_loop() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.dreaming_interval)
        try:
            created = await asyncio.to_thread(_dream_once)
            logger.info("nightly dreaming run produced %s candidates", created)
        except Exception:  # noqa: BLE001
            logger.exception("nightly dreaming run failed")


def register_scheduler(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _start_jobs() -> None:
        settings = get_settings()
        if settings.classify_sweep_enabled:
            app.state.sweep_task = asyncio.create_task(_sweep_loop())
        if settings.dreaming_enabled:
            app.state.dream_task = asyncio.create_task(_dream_loop())

    @app.on_event("shutdown")
    async def _stop_jobs() -> None:
        for attr in ("sweep_task", "dream_task"):
            task = getattr(app.state, attr, None)
            if task is not None:
                task.cancel()
