#!/usr/bin/env python3

"""
Module providing a command-line interface for the WebsiteCrawler
"""

import typing
import argparse
import urllib.parse

try:
    from . import constants
except ImportError:
    import constants


def setup_cli() -> argparse.ArgumentParser:
    """
    Setup the command-line interface

    :return: argument parser
    """

    def location(arg: str) -> str:
        """
        Ensure that a given argument is a valid URL for the downloader

        :param arg: argument as given by the user
        :return: the same, unmodified string
        :raises ValueError: in case the string seems to be invalid
        """

        parsed_value = urllib.parse.urlparse(arg)
        if parsed_value.netloc == "" or parsed_value.scheme == "":
            raise ValueError
        if parsed_value.scheme not in ("http", "https"):
            raise ValueError
        return arg

    def add_boolean_argument(
            group,
            positive: typing.Tuple[str, str],
            negative: typing.Tuple[str, str],
            constant: bool,
            **kwargs
    ):
        """
        Add a boolean option to the given argument group

        :param group: argument group (``argparse._ArgumentGroup`` object)
        :param positive: tuple of an option name and its help message
        :param negative: tuple of an option name and its help message
        :param constant: determine whether to use the positive or negative way
        :param kwargs: dict of arguments for ``add_argument``
        """

        if not constant:
            group.add_argument(
                positive[0],
                help=positive[1],
                action="store_true",
                **kwargs
            )
        else:
            group.add_argument(
                negative[0],
                help=negative[1],
                action="store_false",
                **kwargs
            )

    parser = argparse.ArgumentParser(
        add_help=False,
        description="WebsiteCrawler: a deep website cloning tool"
    )

    mandatory_group = parser.add_argument_group("mandatory arguments")

    mandatory_group.add_argument(
        "websites",
        help="website root URL, usually the domain name with http(s)://",
        type=location,
        nargs="+"
    )

    mandatory_group.add_argument(
        "target_directory",
        help="target base directory to store website files",
        metavar="target"
    )

    content_selection_group = parser.add_argument_group("content selection arguments")

    add_boolean_argument(
        content_selection_group,
        ("--hyperlinks", "allow following hyperlinks to other resources"),
        ("--no-hyperlinks", "deny following hyperlinks to other resources"),
        constants.DEFAULT_INCLUDE_HYPERLINKS,
        dest="include_hyperlinks"
    )

    add_boolean_argument(
        content_selection_group,
        ("--css", "allow inclusion of CSS files"),
        ("--no-css", "deny inclusion of CSS files"),
        constants.DEFAULT_INCLUDE_STYLESHEETS,
        dest="include_stylesheets"
    )

    add_boolean_argument(
        content_selection_group,
        ("--javascript", "allow inclusion of JavaScript files"),
        ("--no-javascript", "deny inclusion of JavaScript files"),
        constants.DEFAULT_INCLUDE_JAVASCRIPT,
        dest="include_javascript"
    )

    add_boolean_argument(
        content_selection_group,
        ("--images", "allow inclusion of image files"),
        ("--no-images", "deny inclusion of image files"),
        constants.DEFAULT_INCLUDE_IMAGES,
        dest="include_images"
    )

    add_boolean_argument(
        content_selection_group,
        ("--fonts", "allow inclusion of linked fonts"),
        ("--no-fonts", "deny inclusion of linked fonts"),
        constants.DEFAULT_INCLUDE_FONTS,
        dest="include_fonts"
    )

    add_boolean_argument(
        content_selection_group,
        ("--third-party", "allow inclusion of resources from third-party locations"),
        ("--no-third-party", "deny inclusion of resources from third-party locations"),
        constants.DEFAULT_INCLUDE_THIRD_PARTY_RESOURCES,
        dest="include_third_party_resources",
    )

    handler_group = parser.add_argument_group("file handling arguments")

    add_boolean_argument(
        handler_group,
        ("--overwrite", "allow overwriting existing local files"),
        ("--no-overwrite", "deny overwriting existing local files"),
        constants.DEFAULT_ALLOW_OVERWRITING_FILES,
        dest="allow_overwrites"
    )

    add_boolean_argument(
        handler_group,
        ("--rewrite", "allow rewriting references to other local files"),
        ("--no-rewrite", "deny rewriting references to other local files"),
        constants.DEFAULT_REWRITE_REFERENCES,
        dest="rewrite_references"
    )

    add_boolean_argument(
        handler_group,
        ("--ascii", "always ensure ASCII chars for filenames and references"),
        ("--no-ascii", "do not ensure ASCII chars for filenames and references"),
        constants.DEFAULT_ASCII_ONLY_REFERENCES,
        dest="ascii_only"
    )

    add_boolean_argument(
        handler_group,
        ("--lowered", "always ensure lowercase filenames and references"),
        ("--no-lowered", "do not ensure lowercase filenames and references"),
        constants.DEFAULT_LOWERED_PATHS,
        dest="lowered_paths"
    )

    add_boolean_argument(
        handler_group,
        ("--unique", "always ensure unique filenames and references"),
        ("--no-unique", "do not ensure unique filenames and references"),
        constants.DEFAULT_UNIQUE_FILENAMES,
        dest="unique_filenames"
    )

    add_boolean_argument(
        handler_group,
        ("--prettify-html", "prettify downloaded HTML files for improved readability"),
        ("--no-prettify-html", "do not prettify downloaded HTML files for improved readability"),
        constants.DEFAULT_PRETTY_HTML,
        dest="pretty_html"
    )

    add_boolean_argument(
        handler_group,
        ("--prettify-css", "prettify downloaded CSS files for improved readability"),
        ("--no-prettify-css", "do not prettify downloaded CSS files for improved readability"),
        constants.DEFAULT_PRETTY_HTML,
        dest="pretty_css"
    )

    add_boolean_argument(
        handler_group,
        ("--prettify-js", "prettify downloaded JS files for improved readability"),
        ("--no-prettify-js", "do not prettify downloaded JS files for improved readability"),
        constants.DEFAULT_PRETTY_HTML,
        dest="pretty_javascript"
    )

    connectivity_group = parser.add_argument_group("connectivity arguments")

    https_mode = connectivity_group.add_mutually_exclusive_group()
    https_mode.add_argument(
        "--http-only",
        help="try enforcing HTTP mode on all connections",
        dest="https_mode",
        action="store_const",
        const=constants.HTTPSMode.HTTP_ONLY,
        default=constants.HTTPSMode.DEFAULT
    )
    https_mode.add_argument(
        "--https-only",
        help="try enforcing HTTPS mode on all connections",
        dest="https_mode",
        action="store_const",
        const=constants.HTTPSMode.HTTPS_ONLY
    )
    https_mode.add_argument(
        "--https-first",
        help="try HTTPS mode first, then fall back to HTTP on errors",
        dest="https_mode",
        action="store_const",
        const=constants.HTTPSMode.HTTPS_FIRST
    )

    connectivity_group.add_argument(
        "--user-agent",
        help="use this custom user agent string for the HTTP(S) requests",
        dest="user_agent",
        metavar="UA",
        default=constants.DEFAULT_USER_AGENT
    )

    processor_group = parser.add_argument_group("processing arguments")

    add_boolean_argument(
        processor_group,
        ("--crash", "always exit runner threads on failure"),
        ("--no-crash", "do not exit runner threads on failure"),
        constants.DEFAULT_RUNNER_CRASH_ON_ERROR,
        dest="crash_on_error"
    )

    processor_group.add_argument(
        "--logfile",
        help="path to the logfile (otherwise stdout)",
        dest="logfile",
        metavar="PATH"
    )

    processor_group.add_argument(
        "--status",
        help="print current status messages to stderr every N seconds",
        dest="status_updates",
        metavar="N",
        type=float,
        default=0
    )

    processor_group.add_argument(
        "--threads",
        help="number of parallel download streams",
        dest="threads",
        default=4,
        metavar="N",
        type=int
    )

    misc_group = parser.add_argument_group("miscellaneous arguments")

    misc_group.add_argument(
        "-h",
        "--help",
        help="show this help message and exit",
        action="help",
        default=argparse.SUPPRESS
    )

    misc_group.add_argument(
        "-v",
        "--verbose",
        help="print verbose information",
        dest="verbose",
        action="store_true"
    )

    misc_group.add_argument(
        "-V",
        "--version",
        help="show version information and exit",
        action="version",
        version=constants.VERSION_STRING,
        default=argparse.SUPPRESS
    )

    return parser


if __name__ == "__main__":
    setup_cli().parse_args(["--help"])
