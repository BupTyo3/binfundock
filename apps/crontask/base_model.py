from utils.framework.models import SingletonModel


class CronTaskBase(SingletonModel):
    pass

    class Meta:
        abstract = True
