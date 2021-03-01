#!/usr/bin/env python3

import os
import queue
import logging
import argparse
import threading


QUEUE_ACCESS_TIMEOUT = 0.5


class Downloader:
    """
    Downloader for website content, filtering duplicates, extracting more targets
    """

    def __init__(self, website: str, target: str, logger: logging.Logger):
        self.website = website
        self.target = target
        self.logger = logger

        if not os.path.exists(target):
            os.makedirs(target, exist_ok=True)
        elif not os.path.isdir(target):
            logger.critical("Target directory is no directory!")
            raise RuntimeError("Target directory is no directory!")

        self.downloads = []
        self.runners = []
        self.queue = queue.Queue()

        self.queue.put(website)

    def start_runner(self, suffix: str):
        """
        Start a runner in a separate thread

        :param suffix: identification suffix added to the logger name
        """

        r = _Runner(suffix, self)
        self.runners.append(r)
        threading.Thread(target=r.run, daemon=False).start()


class _Runner:
    """
    Worker to perform the actual task of downloading, extracting, storing
    """

    def __init__(self, suffix: str, downloader: Downloader):
        self.downloader = downloader
        self.queue = self.downloader.queue
        self.logger = self.downloader.logger.getChild(suffix)

        self.started = False
        self.running = False

    def stop(self):
        """
        Stop the runner (which will just finish the last job before exiting)
        """

        self.running = False

    def run(self):
        """
        Perform the actual work in a loop
        """

        self.logger.debug(f"Starting running loop for {self} ...")

        self.started = True
        self.running = True

        while self.running and not self.queue.empty():
            next_job = self.queue.get(True, QUEUE_ACCESS_TIMEOUT)
            pass  # TODO


def setup() -> argparse.ArgumentParser:
    """
    Setup the command-line interface

    :return: argument parser
    """

    parser = argparse.ArgumentParser(
        description="MateBot maintaining command-line interface"
    )

    parser.add_argument(
        "website",
        help="website root URL, typically the domain name"
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
        "--logfile",
        help="path to the logfile",
        dest="logfile",
        metavar="file"
    )

    parser.add_argument(
        "--threads",
        help="number of parallel download streams",
        dest="threads",
        default=4,
        metavar="n",
        type=int
    )

    return parser


def main(website: str, target: str, verbose: bool, logfile: str, threads: int):
    if logfile:
        logging.basicConfig(
            level=logging.INFO if not verbose else logging.DEBUG,
            filename=logfile,
            # format=""  # TODO
        )
    else:
        logging.basicConfig(
            level=logging.INFO if not verbose else logging.DEBUG,
            # format=""  # TODO
        )

    logger = logging.getLogger("crawler")
    downloader = Downloader(website, target, logger)
    for i in range(threads):
        downloader.start_runner(f"runner{i}")


if __name__ == "__main__":
    namespace = setup().parse_args()
    main(
        namespace.website,
        namespace.target,
        namespace.verbose,
        namespace.logfile,
        namespace.threads
    )
