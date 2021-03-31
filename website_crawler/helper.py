#!/usr/bin/env python3

import typing
import urllib.parse

from . import constants as _constants


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
        fallback: str = _constants.DEFAULT_ASCII_REPLACEMENT_CHAR
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


def remove_dot_segments(path: str) -> str:
    """
    Remove the dot segments of a given path

    The implementation of this method was inspired
    by RFC 3986, section 5.2.4, but uses another,
    much easier and yet probably equivalent algorithm.

    :param path: any path that may contain dot segments
    :return: path without dot segments
    """

    out = []

    for segment in path.split("/"):
        if segment == "" or segment == ".":
            pass
        elif segment == "..":
            if len(out) > 0:
                out.pop()
        else:
            out.append(segment)

    return "/" + "/".join(out)


def find_absolute_reference(
        target: str,
        domain: str,
        remote_url: urllib.parse.ParseResult,
        https_mode: int = _constants.DEFAULT_HTTPS_MODE,
        base: typing.Optional[urllib.parse.ParseResult] = None
) -> typing.Optional[str]:
    """
    Transform the partly defined target string to a full URL

    The implementation of this method is partly based
    on RFC 3986, section 5.1 and 5.2 (with modifications).

    :param target: anything that seems to be an URI, relative or absolute
    :param domain: remote network location name (usually domain name)
    :param remote_url: remote URL that was used before, i.e. the referrer
        to the new target (and most likely also the origin of the reference)
    :param https_mode: definition how to treat the HTTPS mode (for the scheme)
    :param base: optional base URI used to correctly find absolute paths
        for relative resource indicators (uses the remote URL if absent)
    :return: a full URL that can be used to request further resources,
        if possible and the target matched the criteria (otherwise None);
        one of those criteria is the same remote netloc, which is enforced
        to limit the width of our requests to not query the whole web
    """

    def merge_paths(a: urllib.parse.ParseResult, b: str) -> str:
        """
        Merge two paths, where `a` should be a base and `b` should be a reference
        """

        if not b.startswith("/"):
            b = "/" + b
        if a.netloc != "" and a.path == "":
            return b
        return "/".join(a.path.split("/")[:-1]) + b

    url = urllib.parse.urlparse(target)
    scheme, netloc, path, params, query, fragment = url

    # TODO: section 5.1, order of precedence
    if base is None:
        base = remote_url

    # Unknown schemes are ignored (e.g. mailto:) and a given schema indicates
    # an absolute URL which should not be processed (only filtered)
    if scheme != "" and scheme.lower() not in ("http", "https"):
        return
    elif scheme == "":
        if https_mode == 0:
            scheme = remote_url.scheme
        elif https_mode == 1 or https_mode == 3:
            scheme = "https"
        elif https_mode == 2:
            scheme = "http"
    elif netloc != "" and netloc.lower() == domain.lower():
        return urllib.parse.urlunparse(
            (scheme, netloc, remove_dot_segments(path), params, query, "")
        )

    # Other network locations are ignored (so we don't traverse the whole web)
    if netloc != "" and netloc.lower() != domain.lower():
        return
    elif netloc != "":
        return urllib.parse.urlunparse(
            (scheme, netloc, remove_dot_segments(path), params, query, "")
        )

    netloc = domain

    # Determine the new path
    if path == "":
        path = base.path
        if query == "":
            query = base.query
    else:
        if path.startswith("/"):
            path = remove_dot_segments(path)
        else:
            path = remove_dot_segments(merge_paths(base, path))
    return urllib.parse.urlunparse(
        (scheme, netloc, remove_dot_segments(path), params, query, "")
    )
