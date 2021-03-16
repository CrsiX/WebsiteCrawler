"""
WebsiteCrawler: a deep website cloning tool
"""

from logging import Logger as _Logger
from argparse import Namespace as _Namespace

from downloader import Downloader


def construct_from_namespace(namespace: _Namespace, logger: _Logger) -> Downloader:
    """
    Construct a new Downloader instance from a Namespace object

    :param namespace: a Namespace object filled with the required attributes
    :param logger: logger used for the Downloader and to get runners' loggers
    :return: a fresh Downloader instance constructed from the given namespace
    :raises AttributeError: in case a required namespace attribute is missing
    """

    https_mode = 0
    if namespace.https_only:
        https_mode = 1
    elif namespace.http_only:
        https_mode = 2
    elif namespace.https_first:
        https_mode = 3

    return Downloader(
        website=namespace.website,
        target=namespace.target,
        logger=logger,
        https_mode=https_mode,
        base_ref=namespace.base_ref,
        load_hyperlinks=namespace.explore,
        load_css=namespace.css_download,
        load_js=namespace.javascript_download,
        load_image=namespace.image_download,
        rewrite_references=namespace.rewrite,
        lowered=namespace.lowered,
        third_party=namespace.third_party,
        prettify=namespace.prettify,
        overwrite=namespace.overwrite,
        ascii_only=namespace.ascii_only,
        unique_filenames=namespace.unique_filenames,
        user_agent=namespace.user_agent,
        crash_on_error=namespace.crash_on_error
    )
