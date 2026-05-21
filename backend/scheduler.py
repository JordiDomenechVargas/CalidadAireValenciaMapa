"""Scheduler en segundo plano que regenera el snapshot cada N minutos."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import REFRESH_INTERVAL_MINUTES
from .snapshot import regenerate_snapshot

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """Arranca el scheduler. Idempotente — si ya está arrancado lo devuelve sin más."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        regenerate_snapshot,
        trigger="interval",
        minutes=REFRESH_INTERVAL_MINUTES,
        id="refresh_snapshot",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler iniciado · refresco cada %d min", REFRESH_INTERVAL_MINUTES)
    return _scheduler


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
