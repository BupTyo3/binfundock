

class PairNotExistsError(ValueError):
    """
    If the Pair doesn't exist into the Market
    """
    def __init__(self, symbol='', market='', add_message=''):
        message = f"Pair {symbol} does not exist in Market {market}"
        super().__init__('; '.join((message, add_message)))
