from utils.framework.models import BinfunError


class MainCoinNotServicedError(BinfunError):
    def __init__(self, message="Provided main coin is not serviced"):
        super().__init__(message)


class ShortSpotCombinationError(BinfunError):
    def __init__(self, signal='', add_message=''):
        message = f"Can't create SHORT to SPOT. SignalOrig: '{signal}'"
        super().__init__('; '.join((message, add_message)))


class IncorrectSignalPositionError(BinfunError):
    def __init__(self, signal='', add_message=''):
        message = f"Can't create Signal due to incorrect position. SignalOrig: '{signal}'"
        super().__init__('; '.join((message, add_message)))


class DuplicateSignalError(BinfunError):
    def __init__(self, signal='', market='', add_message=''):
        message = f"Can't create Signal due to a similar " \
                  f"Signal already exists. SignalOrig: '{signal}' in Market '{market}'"
        super().__init__('; '.join((message, add_message)))


class SymbolAlreadyStartedError(BinfunError):
    def __init__(self, signal='', market='', add_message=''):
        message = f"Can't create Signal due to there is a started " \
                  f"Signal with this symbol. SignalOrig: '{signal}' in Market '{market}'"
        super().__init__('; '.join((message, add_message)))
