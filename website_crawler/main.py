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


class FurtherResourceSearcher(html.parser.HTMLParser):
    """
    HTML parser scanning for further targets
    """

    def __init__(self, logger: logging.Logger, hyperlinks: bool, css: bool, js: bool):
        super().__init__()
        self.logger = logger
        self.hyperlinks = hyperlinks
        self.css = css
        self.js = js
        self.results = []

    def error(self, message):
        self.logger.error(f"HTML parsing failed: {message}")

    def handle_starttag(self, tag, attrs):
        def _get_link(attr):
            return list(map(
                lambda x: x[1],
                filter(
                    lambda x: x[0] == attr,
                    attrs
                )
            ))

        if tag == "link" and self.css and ("rel", "stylesheet") in attrs:
            self.results += _get_link("href")

        elif tag == "a" and self.hyperlinks:
            self.results += _get_link("href")

        elif tag == "script" and self.js and ("type", "text/javascript") in attrs:
            self.results += _get_link("src")

        elif tag == "script" and self.js:
            self.logger.warning(f"Ignoring tag 'script' due to missing 'type' in {attrs}")


class Downloader:
    """
    Downloader for website content, filtering duplicates, extracting more targets

    :param website: base URI of the website which should be downloaded
    :param target: target directory where to store downloaded files
    :param logger: logger used to keep track of various events
    :param https_mode: whether to enforce or reject HTTPS connections
        (valid values are 0: don't do anything, 1: enforce HTTPS, 2: enforce HTTP)
    :param base_ref: string for the `base` HTML tag (if it's None, the base ref
        element won't be touched, no matter if it exists; if it's the empty string,
        the base reference will be removed from the resulting markup)
    :param load_hyperlinks: determine whether HTML files from `a` tags should be loaded
    :param load_css: determine whether CSS files from `style` tags should be loaded
    :param load_js: determine whether JavaScript files from `script` tags should be loaded
    :param load_image: determine whether image files from `img` tags should be loaded
    :param rewrite_references: determine whether references to other pages on the same
        site should be rewritten (aka absolute links in `a` tags will now be relative
        links that will probably work with your downloaded files)
    """

    def __init__(
            self,
            website: str,
            target: str,
            logger: logging.Logger,
            https_mode: int = 0,
            base_ref: typing.Optional[str] = None,
            load_hyperlinks: bool = True,
            load_css: bool = False,
            load_js: bool = False,
            load_image: bool = False,
            rewrite_references: bool = False
    ):
        self.website = website
        self.target = target
        self.logger = logger

        self.https_mode = https_mode
        self.base_ref = base_ref
        self.load_hyperlinks = load_hyperlinks
        self.load_css = load_css
        self.load_js = load_js
        self.load_image = load_image
        self.rewrite_references = rewrite_references

        if self.base_ref is not None:
            self.logger.warning("Feature not supported yet: base_ref")
        if self.load_image:
            self.logger.warning("Feature not supported yet: load_image")
        if self.rewrite_references:
            self.logger.warning("Feature not supported yet: rewrite_references")

        self.netloc = urllib.parse.urlparse(self.website).netloc

        if https_mode not in (0, 1, 2):
            logger.error(f"Unknown https mode detected: {https_mode}")
            logger.warning("Set https mode to default value.")
            self.https_mode = 0

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

    def _get_storage_path(
            self,
            path: typing.Union[str, urllib.parse.ParseResult],
            logger: logging.Logger
    ) -> str:
        """
        Return the local storage path in the file system, based on the URI path

        :param path: path of the URI or a ParseResult from `urlparse`
        :param logger: logger for this particular job
        :return: path to a local file (which may not exist yet)
        """

        if isinstance(path, urllib.parse.ParseResult):
            path = path.path
        if path.startswith("/"):
            path = path[1:]

        filename = os.path.join(self.target, path)
        if filename.endswith("/"):
            logger.warning(f"Filename '{filename}' ending with '/' (adding suffix 'index.html')")
            filename = os.path.join(filename, "index.html")
        return filename

    @staticmethod
    def _store(filename: str, content: typing.Union[bytes, str], logger: logging.Logger):
        """
        Store the specified content at the location on disk, creating parent dirs

        :param filename: filename which should be used to store the content
        :param content: result of the request for that path
        :param logger: logger for this particular job
        """

        if isinstance(content, str):
            mode = "w"
        elif isinstance(content, bytes):
            mode = "wb"
        else:
            logger.critical("content must be bytes or str")
            raise TypeError("content must be bytes or str")

        logger.debug(f"Writing to '{filename}' ...")
        os.makedirs(os.path.split(filename)[0], exist_ok=True)
        with open(filename, mode) as f:
            logger.debug(f"{f.write(content)} bytes written.")

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
        searcher = FurtherResourceSearcher(
            logger, self.load_hyperlinks, self.load_css, self.load_js
        )
        searcher.feed(request.text)

        filename = self._get_storage_path(urllib.parse.urlparse(url), logger)
        self._store(filename, request.content, logger)

        # Ensure that no cross-site references are added
        result = []
        for ref in searcher.results:
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

    @classmethod
    def from_namespace(cls, namespace: argparse.Namespace, logger: logging.Logger):
        """
        Construct a new Downloader instance from a Namespace object

        :param namespace: a Namespace object filled with the required attributes
        :param logger: base logger used to construct runners' loggers
        :return: a fresh Downloader instance constructed from the given namespace
        :raises AttributeError: in case a required namespace attribute is missing
        """

        return Downloader(
            website=namespace.website,
            target=namespace.target,
            logger=logger,
            https_mode=namespace.https_mode,
            base_ref=namespace.base_ref,
            load_hyperlinks=namespace.explore,
            load_css=namespace.css_download,
            load_js=namespace.javascript_download,
            load_image=namespace.image_download,
            rewrite_references=namespace.rewrite
        )


def setup() -> argparse.ArgumentParser:
    """
    Setup the command-line interface

    :return: argument parser
    """

    parser = argparse.ArgumentParser(
        description="WebsiteCrawler: a deep website cloning tool"
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
        "--base",
        help="set or remove the base tag (if existing)",
        dest="base_ref",
        metavar="ref",
        default=None
    )

    parser.add_argument(
        "--css",
        help="specify download of CSS content",
        dest="css_download",
        action="store_true"
    )

    parser.add_argument(
        "--https",
        help="https support mode (enforce or reject HTTPS connections)",
        dest="https_mode",
        metavar="mode",
        type=int,
        choices=[0, 1, 2]
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
        "--no-explore",
        help="deny further exploration using a tags and references",
        dest="explore",
        action="store_false"
    )

    parser.add_argument(
        "--rewrite",
        help="switch to rewrite hyperlink references to other downloaded content",
        dest="rewrite",
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

    return parser


def main(namespace: argparse.Namespace):
    level = logging.INFO
    if "verbose" in namespace and namespace.verbose:
        level = logging.DEBUG

    if "logfile" not in namespace or not namespace.logfile:
        logging.basicConfig(
            level=level,
            # format=""  # TODO
        )
    else:
        logging.basicConfig(
            level=level,
            filename=namespace.logfile,
            # format=""  # TODO
        )

    logger = logging.getLogger("crawler")
    downloader = Downloader.from_namespace(namespace, logger)
    for i in range(namespace.threads):
        downloader.start_runner(f"runner{i}")


if __name__ == "__main__":
    main(setup().parse_args())
