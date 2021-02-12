import os
import logging
import random

from logging.handlers import RotatingFileHandler
from celery import Celery
from celery.signals import after_setup_logger
from django.conf import settings

from binfun.settings import conf_obj


# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'binfun.settings')

app = Celery('binfun')

app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


# Override Celery logger
@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    formatter = logging.Formatter(
        '[%(asctime)s] [%(process)d] [%(levelname)s] '
        '[%(name)s] %(message)s'
    )

    # FileHandler
    fh = RotatingFileHandler(
        f'{settings.BASE_DIR}/logs/celery.log',
        maxBytes=1024*1024*10,  # 10 Mb
        backupCount=100)
    fh.setFormatter(formatter)
    logger.addHandler(fh)


_COMMON_CRON_PERIOD_SECS = conf_obj.common_period_of_cron_celery_tasks_secs
_THIRTY_PERCENT_FROM_UNIT = 0.3
# _COMMON_EXPIRES_OF_CRON_TASK_SECS = 9  # I think it should be a bit less than _COMMON_CRON_PERIOD_SECS
_COMMON_EXPIRES_OF_CRON_TASK_SECS = _COMMON_CRON_PERIOD_SECS - (
        _COMMON_CRON_PERIOD_SECS * _THIRTY_PERCENT_FROM_UNIT)
_COMMON_CRON_DELTA_SECS = 0.33
_NUMBER_A_BIT_MORE_THAN_NUMBER_OF_CRON_TASKS = 12
_LIST_OF_DELTAS_FACTOR = [i for i in range(_NUMBER_A_BIT_MORE_THAN_NUMBER_OF_CRON_TASKS)]
random.shuffle(_LIST_OF_DELTAS_FACTOR)


app.conf.beat_schedule = {
    # FIRST FORMING
    "first_forming_cron_task": {
        "task": "apps.signal.tasks.first_forming_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # PUSH JOB
    "push_job_cron_task": {
        "task": "apps.signal.tasks.push_job_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # PULL JOB
    "pull_job_cron_task": {
        "task": "apps.signal.tasks.pull_job_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # BOUGHT WORKER
    "bought_worker_cron_task": {
        "task": "apps.signal.tasks.bought_worker_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # SOLD WORKER
    "sold_worker_cron_task": {
        "task": "apps.signal.tasks.sold_worker_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # SPOIL WORKER
    "spoil_worker_cron_task": {
        "task": "apps.signal.tasks.spoil_worker_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # CLOSE WORKER
    "close_worker_cron_task": {
        "task": "apps.signal.tasks.close_worker_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # TRAIL WORKER
    "trailing_stop_worker_cron_task": {
        "task": "apps.signal.tasks.trailing_stop_worker_parent_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": _COMMON_CRON_PERIOD_SECS + (_COMMON_CRON_DELTA_SECS * _LIST_OF_DELTAS_FACTOR.pop()),
    },
    # UPDATE PRICES WORKER
    "update_prices_task": {
        "task": "apps.pair.tasks.update_prices_task",

        "options": {"expires": _COMMON_EXPIRES_OF_CRON_TASK_SECS},
        "schedule": conf_obj.period_of_prices_update_tasks_secs,
    },
}

