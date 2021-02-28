

class MainCoinNotServicedError(ValueError):
    def __init__(self, message="Provided main coin is not serviced"):
        super().__init__(message)


class ShortSpotCombinationError(ValueError):
    def __init__(self, signal='', add_message=''):
        message = f"Can't create SHORT to SPOT. SignalOrig: '{signal}'"
        super().__init__('; '.join((message, add_message)))


class IncorrectSignalPositionError(ValueError):
    def __init__(self, signal='', add_message=''):
        message = f"Can't create Signal due to incorrect position. SignalOrig: '{signal}'"
        super().__init__('; '.join((message, add_message)))


class DuplicateSignalError(ValueError):
    def __init__(self, signal='', add_message=''):
        message = f"Can't create Signal due to the fact that" \
                  f" a similar Signal already exists. SignalOrig: '{signal}'"
        super().__init__('; '.join((message, add_message)))
