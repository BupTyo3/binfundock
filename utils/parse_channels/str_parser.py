from typing import List


def left_numbers(array: List[str]) -> List[str]:
    """left numbers only (, => .) in array"""
    array = [n.replace('..', '.') for n in array]
    array = [n.replace(' ', '') for n in array]
    array = [n.replace(':', '') for n in array]
    array = list(dict.fromkeys(array))
    possible_array = [''.join([n.replace(',', '.') for n in el if n.isdigit()
                               or n in ['.', ',']]) for el in array]
    return list(filter(None, possible_array))


def check_pair(string):
    if 'Е' in string:
        string = string.replace('Е', 'E')
    if 'О' in string:
        string = string.replace('О', 'O')
    if 'М' in string:
        string = string.replace('М', 'M')
    if 'С' in string:
        string = string.replace('С', 'C')
    if 'Т' in string:
        string = string.replace('Т', 'T')
    if 'В' in string:
        string = string.replace('В', 'B')
    if 'А' in string:
        string = string.replace('А', 'A')
    if 'Н' in string:
        string = string.replace('Н', 'H')
    return string
