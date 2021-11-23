import logging

from celery import shared_task, group
from celery.schedules import crontab

from .models import Signal
from apps.crontask.utils import get_or_create_crontask

logger = logging.getLogger(__name__)


# FIRST FORMING
@shared_task(ignore_result=True)
def first_forming_parent_task():
    if not get_or_create_crontask().first_forming_enabled:
        return
    ids_list = Signal.handle_new_signals(only_get_ids=True)
    group(first_forming_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def first_forming_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.first_formation_orders_by_one_signal()


# PUSH JOB
@shared_task(ignore_result=True)
def push_job_parent_task():
    if not get_or_create_crontask().push_job_enabled:
        return
    ids_list = Signal.push_signals(only_get_ids=True)
    group(push_job_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def push_job_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.push_orders_by_one_signal()


# PULL JOB
@shared_task(ignore_result=True)
def pull_job_parent_task():
    if not get_or_create_crontask().pull_job_enabled:
        return
    ids_list = Signal.update_signals_info_by_api(only_get_ids=True)
    group(pull_job_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def pull_job_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.update_orders_info_by_one_signal()


# BOUGHT WORKER
@shared_task(ignore_result=True)
def bought_worker_parent_task():
    if not get_or_create_crontask().bought_worker_enabled:
        return
    ids_list = Signal.bought_orders_worker(only_get_ids=True)
    group(bought_worker_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def bought_worker_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.worker_for_bought_orders_by_one_signal()


# SOLD WORKER
@shared_task(ignore_result=True)
def sold_worker_parent_task():
    if not get_or_create_crontask().sold_worker_enabled:
        return
    ids_list = Signal.sold_orders_worker(only_get_ids=True)
    group(sold_worker_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def sold_worker_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.worker_for_sold_orders_by_one_signal()


# SPOIL WORKER
@shared_task(ignore_result=True)
def spoil_worker_parent_task():
    if not get_or_create_crontask().spoil_worker_enabled:
        return
    ids_list = Signal.spoil_worker(only_get_ids=True)
    group(spoil_worker_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def spoil_worker_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.try_to_spoil_by_one_signal()


# CLOSE WORKER
@shared_task(ignore_result=True)
def close_worker_parent_task():
    if not get_or_create_crontask().close_worker_enabled:
        return
    ids_list = Signal.close_worker(only_get_ids=True)
    group(close_worker_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def close_worker_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.try_to_close_by_one_signal()


# TRAIL WORKER
@shared_task(ignore_result=True)
def trailing_stop_worker_parent_task():
    if not get_or_create_crontask().trailing_stop_enabled:
        return
    ids_list = Signal.trailing_stop_worker(only_get_ids=True)
    group(trailing_stop_worker_by_one_signal_task.s(i) for i in ids_list).apply_async()


@shared_task(ignore_result=True)
def trailing_stop_worker_by_one_signal_task(signal_id):
    signal = Signal.objects.filter(pk=signal_id).first()
    if signal:
        signal.trail_stop_by_one_signal()
