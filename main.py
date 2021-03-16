#!/usr/bin/env python3

import sys
import time
import logging
import argparse
import threading
import urllib.parse

import website_crawler


_MAIN_SLEEP_TIME = 0.01


def setup() -> argparse.ArgumentParser:
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

    parser = argparse.ArgumentParser(
        description="WebsiteCrawler: a deep website cloning tool"
    )

    parser.add_argument(
        "website",
        help="website root URL, typically the domain name",
        type=location
    )

    parser.add_argument(
        "target",
        help="target base directory to store website files"
    )

    parser.add_argument(
        "-v",
        "--verbose",
        help="print verbose information",
        dest="verbose",
        action="store_true"
    )

    parser.add_argument(
        "--ascii",
        help="use ASCII chars for link and file names only",
        dest="ascii_only",
        action="store_true"
    )

    parser.add_argument(
        "--base",
        help="set or remove the `base` tag (if existing)",
        dest="base_ref",
        metavar="ref",
        type=location,
        default=None
    )

    parser.add_argument(
        "--crash",
        help="exit runner threads on exit (continue otherwise)",
        dest="crash_on_error",
        action="store_true"
    )

    parser.add_argument(
        "--css",
        help="specify download of CSS content",
        dest="css_download",
        action="store_true"
    )

    https_mode = parser.add_mutually_exclusive_group()
    https_mode.add_argument(
        "--http",
        help="try enforcing HTTP mode on all connections",
        dest="http_only",
        action="store_true"
    )
    https_mode.add_argument(
        "--https",
        help="try enforcing HTTPS mode on all connections",
        dest="https_only",
        action="store_true"
    )
    https_mode.add_argument(
        "--https-first",
        help="try HTTPS mode first, then fall back to HTTP on errors",
        dest="https_only",
        action="store_true"
    )

    parser.add_argument(
        "--image",
        help="specify download of content in image tags",
        dest="image_download",
        action="store_true"
    )

    parser.add_argument(
        "--javascript",
        help="specify download of JavaScript content",
        dest="javascript_download",
        action="store_true"
    )

    parser.add_argument(
        "--logfile",
        help="path to the logfile",
        dest="logfile",
        metavar="file"
    )

    parser.add_argument(
        "--lowered",
        help="convert all path names to lowercase",
        dest="lowered",
        action="store_true"
    )

    parser.add_argument(
        "--no-explore",
        help="deny further exploration using `a` tags and references",
        dest="explore",
        action="store_false"
    )

    parser.add_argument(
        "--no-overwrite",
        help="do not overwrite any existing files",
        dest="overwrite",
        action="store_false"
    )

    parser.add_argument(
        "--prettify",
        help="prettify resulting HTML files to improve readability",
        dest="prettify",
        action="store_true"
    )

    parser.add_argument(
        "--rewrite",
        help="rewrite references to other downloaded content",
        dest="rewrite",
        action="store_true"
    )

    parser.add_argument(
        "--status",
        help="print current status messages to stderr every n seconds",
        dest="status",
        metavar="n",
        type=float,
        default=0
    )

    parser.add_argument(
        "--third-party",
        help="also download third party resources (CSS, JS, images only)",
        dest="third_party",
        action="store_true"
    )

    parser.add_argument(
        "--threads",
        help="number of parallel download streams",
        dest="threads",
        default=4,
        metavar="n",
        type=int
    )

    parser.add_argument(
        "--unique",
        help="use unique file names (improves third party usage)",
        dest="unique_filenames",
        action="store_true"
    )

    parser.add_argument(
        "--user-agent",
        help="custom user agent string for the HTTP(S) requests",
        dest="user_agent",
        metavar="x",
        default=None
    )

    return parser


def main(namespace: argparse.Namespace):
    level = logging.INFO
    if "verbose" in namespace and namespace.verbose:
        level = logging.DEBUG

    logging_setup = {
        "level": level,
        "format": "{asctime} [{levelname}] {name}: {message}",
        "datefmt": "%d.%m.%Y %H:%M",
        "style": "{"
    }

    if "logfile" in namespace and namespace.logfile:
        logging_setup["filename"] = namespace.logfile
    logging.basicConfig(**logging_setup)

    logger = logging.getLogger("crawler")
    loader = website_crawler.construct_from_namespace(namespace, logger)
    for i in range(namespace.threads):
        loader.start_runner(f"runner{i}")

    def _print_status():
        while True:
            time.sleep(namespace.status)
            print(loader.get_status(), file=sys.stderr)

    if namespace.status > 0:
        threading.Thread(target=_print_status, daemon=True).start()

    while loader.is_running():
        time.sleep(_MAIN_SLEEP_TIME)

    loader.stop_all_runners()
    logger.info("Finished.")


if __name__ == "__main__":
    main(setup().parse_args())
