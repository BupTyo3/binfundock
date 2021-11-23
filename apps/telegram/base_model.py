from utils.framework.models import SystemBaseModel, SingletonModel


class BaseTelegram(SingletonModel):

    class Meta:
        abstract = True
