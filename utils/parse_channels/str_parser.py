from typing import List


def left_numbers(array: List[str]) -> List[str]:
    """left numbers only (, => .) in array"""
    array = [n.replace('..', '.') for n in array]
    array = [n.replace('\'', '') for n in array]
    array = [n.replace('[', '') for n in array]
    array = [n.replace(']', '') for n in array]
    array = [n.replace(' ', '') for n in array]
    array = [n.replace(':', '') for n in array]
    array = [n.replace(',', '.') for n in array]
    array = [n.replace('-', '') for n in array]
    array = [n.replace('+', '') for n in array]
    array = [n.replace('(', '') for n in array]
    array = [n.replace(')', '') for n in array]
    array = [n.replace('X', '') for n in array]
    array = list(dict.fromkeys(array))
    # possible_array = [''.join([n.replace(',', '.') for n in el if n.isdigit()
    #                            or n in ['.', ',']]) for el in array]
    return list(filter(None, array))


def find_number_in_list(list_of_strings):
    for string in list_of_strings:
        try:
            return float(string)
        except ValueError:
            pass


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
    if 'К' in string:
        string = string.replace('К', 'K')
    if 'Р' in string:
        string = string.replace('Р', 'P')
    if 'У' in string:
        string = string.replace('У', 'Y')
    return string


def replace_rus_to_eng(string):
    if 'е' in string:
        string = string.replace('е', 'e')
    if 'о' in string:
        string = string.replace('о', 'o')
    if 'м' in string:
        string = string.replace('м', 'm')
    if 'с' in string:
        string = string.replace('с', 'c')
    if 'т' in string:
        string = string.replace('т', 't')
    if 'в' in string:
        string = string.replace('в', 'b')
    if 'а' in string:
        string = string.replace('а', 'a')
    if 'н' in string:
        string = string.replace('н', 'h')
    if 'к' in string:
        string = string.replace('к', 'k')
    if 'р' in string:
        string = string.replace('р', 'p')
    if 'у' in string:
        string = string.replace('у', 'y')
    return string
