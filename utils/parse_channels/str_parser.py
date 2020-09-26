from typing import List


def left_numbers(array: List[str]) -> List[str]:
    """left numbers only (, => .) in array"""
    possible_array = [''.join([n.replace(',', '.') for n in el if n.isdigit()
                               or n in ['.', ',']]) for el in array]
    return list(filter(None, possible_array))

