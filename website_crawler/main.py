#!/usr/bin/env python3

import os
import queue
import typing
import logging
import argparse
import threading
import html.parser
import urllib.parse

import requests

USER_AGENT_STRING = "Mozilla/5.0 (compatible; WebsiteCrawler)"
QUEUE_ACCESS_TIMEOUT = 1


class HyperlinkSearcher(html.parser.HTMLParser):
    """
    HTML parser scanning for hyperlink targets only
    """

    def __init__(self, logger: logging.Logger):
        super().__init__()
        self.logger = logger
        self.hyperlinks = []

    def error(self, message):
        self.logger.error(f"HTML parsing failed: {message}")

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hyperlinks += list(map(
                lambda x: x[1],
                filter(
                    lambda x: x[0] == "href",
                    attrs
                )
            ))


class Downloader:
    """
    Downloader for website content, filtering duplicates, extracting more targets

    :param website: base URI of the website which should be downloaded
    :param target: target directory where to store downloaded files
    :param logger: logger used to keep track of various events
    """

    def __init__(
            self,
            website: str,
            target: str,
            logger: logging.Logger
    ):
        self.website = website
        self.target = target
        self.logger = logger
        self.netloc = urllib.parse.urlparse(self.website).netloc

        if not os.path.exists(target):
            os.makedirs(target, exist_ok=True)
            self.logger.debug("Created missing target directory.")
        elif not os.path.isdir(target):
            logger.critical("Target directory is no directory!")
            raise RuntimeError("Target directory is no directory!")

        self.runners = {}
        self.downloads = {}
        self.queue = queue.Queue()

        # A runner's state may be one of the following five options:
        # 0 -> the runner has just been created, it's not running yet
        # 1 -> the runner is up and performing actual work
        # 2 -> the runner is doing something, but it was requested to quit
        # 3 -> the runner exited successfully
        # 4 -> the runner crashed due to an exception
        self._runner_states = {}

        self.queue.put(website)
        self.logger.debug("Initialized downloader.")

    def start_runner(self, key: str) -> bool:
        """
        Start a runner in a separate thread

        :param key: identification key for the runner (and suffix of its logger)
        :return: whether a new runner has been added successfully
        """

        if key in self.runners:
            self.logger.error(f"Couldn't add runner '{key}' as it's already there.")
            return False

        r = threading.Thread(target=self._run, args=(key,), daemon=False)
        self.runners[key] = r
        self._runner_states[key] = 0
        self.logger.debug(f"Added runner '{key}'.")
        r.start()

    def stop_runner(self, key: str, timeout: int) -> bool:
        """
        Join the specified runner (which is a blocking operation)

        :param key: identification key for the runner (and suffix of its logger)
        :param timeout: max time to wait for the worker thread to finish
        :return: whether the runner was found and told to stop
        """

        if key not in self.runners:
            self.logger.warning(f"Runner '{key}' couldn't be stopped: not found.")
            return False

        self._runner_states[key] = 2
        self.runners[key].join(timeout=timeout)
        return True

    def _store(self, path: str, content: typing.Union[bytes, str]):
        """
        Store the specified content at the location 'path' on disk

        :param path: original path on the remote side
        :param content: result of the request for that path
        """

        pass

    def _handle(self, url: str, logger: logging.Logger) -> typing.List[str]:
        """
        Retrieve the content of the given URL, store it and extract more targets

        :param url: target URL which should be downloaded and analysed
        :param logger: logger for this particular job
        :return: list of other, yet unknown URLs found in the content
        """

        logger.debug(f"Currently processing: {url}")
        request = requests.get(url, headers={"User-Agent": USER_AGENT_STRING})
        code = request.status_code

        if not code == 200:
            logger.error(f"Received code {code} for {url}. Skipping.")
            self.downloads[url] = code
            return []

        self.downloads[url] = code
        searcher = HyperlinkSearcher(logger)
        searcher.feed(request.text)

        self._store(urllib.parse.urlparse(url).path, request.content)

        # Ensure that no cross-site references are added
        result = []
        for ref in searcher.hyperlinks:
            if ref.startswith("#"):
                continue
            new_reference = urllib.parse.urljoin(self.website, ref)
            if urllib.parse.urlparse(new_reference).netloc == self.netloc:
                result.append(new_reference)

        return result

    def _run(self, ident: str):
        """
        Perform the actual work in a loop

        :param ident: (hopefully) unique string for runner identification
        """

        logger = self.logger.getChild(ident)
        logger.debug(f"Starting running loop for {ident} ...")
        self._runner_states[ident] = 1

        while self._runner_states[ident] < 2:
            try:
                current_job = self.queue.get(True, QUEUE_ACCESS_TIMEOUT)
            except queue.Empty:
                logger.debug("Queue was empty.")
                continue

            # Avoid duplicates in the queue by reserving the downloads 'slot'
            if current_job in self.downloads:
                continue
            self.downloads[current_job] = 0

            try:
                for item in self._handle(current_job, logger):
                    self.queue.put(item)
            except:
                logger.error(f"Error during handling of '{current_job}'!", exc_info=True)
                self._runner_states[ident] = 4
                raise

        self._runner_states[ident] = 3


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
