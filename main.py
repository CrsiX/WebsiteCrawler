#!/usr/bin/env python3

import sys
import logging

from website_crawler import cli, options, downloader


def main(opts: options.Options, handler_classes=None):
    """
    Run the main program with logging and status already set up

    :param opts: Options storage
    :param handler_classes: optional list of custom handler classes
        as directly passed to the ``DefaultDownloader`` constructor
    """

    logging_setup = {
        "level": logging.DEBUG if opts.verbose else logging.INFO,
        "format": "{asctime} [{levelname}] {name}: {message}",
        "datefmt": "%d.%m.%Y %H:%M:%S",
        "style": "{"
    }

    if opts.logfile:
        logging_setup["filename"] = opts.logfile
    logging.basicConfig(**logging_setup)

    logger = logging.getLogger("crawler")
    status = None
    if opts.status_updates:
        status = (opts.status_updates, lambda *args: print(*args, file=sys.stderr))

    loader_class = downloader.MultiThreadedDownloader
    if opts.threads == 1:
        loader_class = downloader.SingleThreadedDownloader
        if opts.status_updates:
            logger.warning(
                "Status updates are currently not "
                "supported in single-threaded mode!"
            )

    loader = loader_class(
        websites=opts.websites,
        target_directory=opts.target_directory,
        logger=logger,
        options=opts,
        manager_debug_mode=False,
        handler_classes=handler_classes
    )
    loader.run(
        threads=opts.threads,
        status=status
    )


if __name__ == "__main__":
    main(options.Options(**cli.setup_cli().parse_args().__dict__))
