from utils.framework.models import SystemBaseModel, SingletonModel


class Strategy(SingletonModel):

    class Meta:
        abstract = True
