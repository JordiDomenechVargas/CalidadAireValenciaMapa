"""Scheduler en segundo plano con dos jobs:

1. `regenerate_snapshot()` cada REFRESH_INTERVAL_MINUTES (default 60):
   regeneración completa — descarga CSV nuevo, scrape GVA, meteo, etc.

2. `refresh_meteo()` cada METEO_REFRESH_INTERVAL_MINUTES (default 5):
   refresco ligero solo del campo meteo del snapshot. Útil para recuperarse
   rápido de caídas transitorias de Open-Meteo sin esperar al ciclo grande.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from .config import REFRESH_INTERVAL_MINUTES, METEO_REFRESH_INTERVAL_MINUTES
from .snapshot import regenerate_snapshot, refresh_meteo

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """Arranca el scheduler con los dos jobs. Idempotente — si ya está arrancado lo
    devuelve sin más."""
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
    _scheduler.add_job(
        refresh_meteo,
        trigger="interval",
        minutes=METEO_REFRESH_INTERVAL_MINUTES,
        id="refresh_meteo",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler iniciado · snapshot cada %d min, meteo cada %d min",
        REFRESH_INTERVAL_MINUTES, METEO_REFRESH_INTERVAL_MINUTES,
    )
    return _scheduler


def get_scheduler() -> BackgroundScheduler | None:
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
