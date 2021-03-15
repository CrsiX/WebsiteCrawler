#!/usr/bin/env python3

SMALL_ASCII_CONVERSION_TABLE = {
    "ä": "ae",
    "Ä": "Ae",
    "ö": "oe",
    "Ö": "Oe",
    "ü": "ue",
    "Ü": "Ue",
    "ß": "ss"
}


def convert_to_ascii_only(
        string: str,
        mapping: dict = None,
        fallback: str = "_"
) -> str:
    """
    Convert a string containing any kind of characters into an ASCII-only string

    If a symbol of the input string is a key of the specified mapping,
    the value at its position will be used to replace the symbol.
    Otherwise, the fallback character (default: underscore) will be used.
    When no mapping is specified, an empty dictionary will be used.
    Note that len(input) == len(output) won't hold true if arbitrary
    characters and multi-character strings are used as values!

    :param string: any string
    :param mapping: a dictionary where the keys should be single-character
        strings because they will be tried to replace certain non-ASCII chars
    :param fallback: a single character which is used as a fallback,
        i.e. when there's no mapping for a non-ASCII character available
    :return: a string containing only ASCII characters
    """

    if mapping is None:
        mapping = {}

    return "".join(
        c
        if c.isascii()
        else (
            mapping[c]
            if c in mapping
            else fallback
        )
        for c in string
    )
