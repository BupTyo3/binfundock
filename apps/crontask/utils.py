import logging

from apps.crontask.models import CronTask

logger = logging.getLogger(__name__)


def get_or_create_crontask() -> CronTask:
    crontask_obj, created = CronTask.objects.get_or_create()
    if created:
        logger.debug(f"CronTask '{crontask_obj}' has been created")
    return crontask_obj
