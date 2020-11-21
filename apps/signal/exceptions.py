

class MainCoinNotServicedError(ValueError):
    def __init__(self, message="Provided main coin is not serviced"):
        super().__init__(message)


class ShortSpotCombinationError(ValueError):
    def __init__(self, signal='', add_message=''):
        message = f"Can't create SHORT to SPOT. SignalOrig: '{signal}'"
        super().__init__('; '.join((message, add_message)))
