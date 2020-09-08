from model_utils.models import TimeStampedModel


class SystemBaseModel(TimeStampedModel):
    """Base model for models"""

    class Meta:
        abstract = True

