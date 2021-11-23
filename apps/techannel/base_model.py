from utils.framework.models import SystemBaseModel


class TechannelBase(SystemBaseModel):
    abbr: str
    name: str

    class Meta:
        abstract = True
