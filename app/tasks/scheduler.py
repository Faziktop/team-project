"""Инициализация внутрипроцессного планировщика (APScheduler).

Эквивалент требования ТЗ п.4.2.4 «внутрипроцессный планировщик задач
(Flask-APScheduler)» — используется APScheduler напрямую в BackgroundScheduler,
что даёт тот же функциональный результат (задачи по расписанию внутри
процесса приложения) без дополнительной обёртки.
"""
import atexit
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.tasks.reminders import send_due_reminders

logger = logging.getLogger("questevent.scheduler")
_scheduler = None


def init_scheduler(app):
    global _scheduler
    if not app.config.get("SCHEDULER_ENABLED", True):
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(daemon=True)
    interval = app.config.get("REMINDER_POLL_SECONDS", 60)
    scheduler.add_job(lambda: send_due_reminders(app), "interval", seconds=interval, id="send_due_reminders")
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))
    _scheduler = scheduler
    logger.info("Планировщик регламентных задач запущен (интервал=%sс)", interval)
    return scheduler
