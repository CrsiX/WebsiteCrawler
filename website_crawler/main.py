#!/usr/bin/env python3

import os
import time
import queue
import typing
import logging
import argparse
import threading
import urllib.parse

import bs4
import requests

USER_AGENT_STRING = "Mozilla/5.0 (compatible; WebsiteCrawler)"
QUEUE_ACCESS_TIMEOUT = 1


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
        site should be rewritten (e.g. absolute links in `a` tags will now be relative
        links that will probably work with your downloaded files); this procedure
        will be applied to all downloaded files if enabled (e.g. also CSS or JS files)
    :param lowered: determine whether all paths and all references should be converted
        to lowercase characters, fixing errors of file systems not ignoring uppercase
        (this will only be used when `rewrite_references` is also set to True)
    :param third_party: determine whether resources from third parties should be loaded too
    :param prettify: switch to enable prettifying the resulting HTML file to improve
        the file's readability (but may also introduce whitespace errors)
    :param overwrite: allow overwriting existing files (default: True)
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
            rewrite_references: bool = False,
            lowered: bool = False,
            third_party: bool = False,
            prettify: bool = False,
            overwrite: bool = True
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
        self.lowered = lowered
        self.third_party = third_party
        self.prettify = prettify
        self.overwrite = overwrite

        if self.base_ref is not None:
            self.logger.warning("Feature not supported yet: base_ref")
        if self.load_image:
            self.logger.warning("Feature not supported yet: load_image")
        if self.rewrite_references:
            self.logger.warning("Feature not supported yet: rewrite_references")
        if not self.rewrite_references and self.lowered:
            self.logger.info("Feature disabled: lowered")
            self.lowered = False
        if self.lowered:
            self.logger.warning("Feature not supported yet: lowered")

        self.netloc = urllib.parse.urlparse(self.website).netloc
        if self.netloc == "":
            self.logger.error("Empty net location! Further operation might fail.")

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
        # 5 -> the runner skipped an iteration due to an empty queue (running)
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

    def stop_all_runners(self) -> bool:
        """
        Join all runners

        This is a blocking operation. Note that this might take an infinite
        amount of time if the runner is not about to exit.

        :return: success of the operation (whether all runners have exited)
        """

        for key in self.runners:
            if self._runner_states[key] in (0, 1, 5):
                self._runner_states[key] = 2
                self.logger.debug(f"Set runner state of '{key}' -> 2")
            elif self._runner_states[key] == 3:
                self.logger.debug(f"Runner '{key}' seems to have already finished")
            elif self._runner_states[key] == 4:
                self.logger.debug(f"Runner '{key}' seems to have already crashed")

        for key in self.runners:
            self.runners[key].join()
            self.logger.debug(f"Stopped runner '{key}'")

        return True

    def is_running(self) -> bool:
        """
        Determine whether the workers are currently doing something

        :return: whether at least one runner is working on something
        """

        return any(map(
            lambda k: self._runner_states[k] in (0, 1, 2),
            self._runner_states
        ))

    def _run(self, ident: str):
        """
        Perform the actual work in a loop

        :param ident: (hopefully) unique string for runner identification
        """

        logger = self.logger.getChild(ident)
        logger.debug(f"Starting running loop for {ident} ...")
        self._runner_states[ident] = 1

        while self._runner_states[ident] < 2 or self._runner_states[ident] == 5:
            try:
                current_job = self.queue.get(True, QUEUE_ACCESS_TIMEOUT)
                self._runner_states[ident] = 1
            except queue.Empty:
                if self._runner_states[ident] < 2:
                    self._runner_states[ident] = 5
                continue

            # Avoid duplicates in the queue by reserving the downloads 'slot'
            if current_job in self.downloads:
                continue
            self.downloads[current_job] = 0

            try:
                worker = DownloadWorker(current_job, logger, self)
                worker.run()
                for item in set(worker.references):
                    if item not in self.downloads:
                        self.queue.put(item)
                self.downloads[current_job] = worker.code
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
            rewrite_references=namespace.rewrite,
            third_party=namespace.third_party,
            prettify=namespace.prettify,
            overwrite=namespace.overwrite
        )


class DownloadWorker:
    """
    Worker class performing the actual work of downloading, analyzing, storing, ...

    :param url: string containing the URL that should be processed
    :param logger: the logger which should be used
    :param downloader: a reference to the Downloader object to get more details
    """

    def __init__(self, url: str, logger: logging.Logger, downloader: Downloader):
        self.url: str = url
        """URL that should be requested from the server, analyzed and stored"""
        self.logger: logging.Logger = logger
        """Logger which will be used for logging"""
        self.downloader: Downloader = downloader
        """Reference to the Downloader object to access certain attributes (read-only)"""

        self.base: typing.Optional[str] = None
        """URI as extracted from the `base` HTML tag, if available"""
        self.code: typing.Optional[int] = None
        """HTTP response code of the request"""
        self.html: typing.Optional[bool] = None
        """Indicator whether the response was handled as HTML result"""
        self.filename: typing.Optional[str] = None
        """Path in the local file system where the file is stored, may be relative"""
        self.references: typing.Set[str] = set()
        """Set of references (URLs) to other server resources found in the response"""

        # All those attributes should be considered an implementation
        # detail, despite being 'public' by convention
        self.soup: typing.Optional[bs4.BeautifulSoup] = None
        """BeautifulSoup object containing the tree of the HTML response, if possible"""
        self.response: typing.Optional[requests.Response] = None
        """Response of the web server, answering the request for the URL"""
        self.content_type: typing.Optional[str] = None
        """Content type of the response, as determined by the HTTP header"""
        self.final_content: typing.Union[bytes, str, None] = None
        """Final version of the content as stored in the target file"""

        self.started: bool = False
        """Information whether the processing of the URL has been started"""
        self.written: bool = False
        """Information whether the content has been written to the desired filename"""
        self.finished: bool = False
        """Information whether the processing of the URL has been finished"""

    def _handle_hyperlinks(self):
        """
        Handle all `a` tags occurring in the file (represented as soup)

        This method extracts the URLs of all hyperlink references of `a` tags
        and adds them to the set of references if it matches the criteria. If rewriting
        of references had been enabled, this step will also be done in this method.
        """

        for tag in self.soup.find_all("a"):
            if tag.has_attr("href"):
                target = tag.get("href")
                if target.startswith("#"):
                    continue

                url = urllib.parse.urlparse(target)
                if url.scheme != "" and url.scheme not in ("http", "https"):
                    continue
                if url.netloc != "" and url.netloc != self.downloader.netloc:
                    continue

                # TODO: respect the base value

                self.references.add(target)

    def _handle_links(self):
        """
        Handle all `link` tags occurring in the file (represented as soup)

        This method extracts the URLs of all external resources mentioned in `link` tags
        and adds them to the set of references if it matches the criteria. If rewriting
        of references had been enabled, this step will also be done in this method.
        """

        self.logger.debug("_handle_links is not implemented yet.")

    def _handle_scripts(self):
        """
        Handle all `script` tags occurring in the file (represented as soup)

        This method extracts the URLs of all external resources mentioned in `script` tags
        and adds them to the set of references if it matches the criteria. If rewriting
        of references had been enabled, this step will also be done in this method.
        """

        self.logger.debug("_handle_scripts is not implemented yet.")

    def _handle_images(self):
        """
        Handle all `img` tags occurring in the file (represented as soup)

        This method extracts the URLs of all external resources mentioned in `img` tags
        and adds them to the set of references if it matches the criteria. If rewriting
        of references had been enabled, this step will also be done in this method.
        """

        self.logger.debug("_handle_images is not implemented yet.")

    def run(self):
        """
        Perform the actual work as a blocking process
        """

        # Restrict multiple (unintentional) calls to this method
        if self.started or self.finished:
            return
        self.started = True

        self.logger.debug(f"Currently processing: {self.url}")
        self.response = requests.get(self.url, headers={"User-Agent": USER_AGENT_STRING})
        self.code = self.response.status_code

        if self.code != 200:
            self.logger.error(f"Received code {self.code} for {self.url}. Skipping.")
            return

        # Determine the content type of the response to only analyze HTML responses
        if "Content-Type" in self.response.headers:
            self.content_type = self.response.headers["Content-Type"]

        # Generate the 'soup' and extract the base reference, if possible
        if self.content_type.lower().startswith("text/html"):
            self.soup = bs4.BeautifulSoup(self.response.text, features="html.parser")
            self.base = self.downloader.netloc
            if self.soup.base is not None and self.soup.base.has_attr("href"):
                self.base = self.soup.base.get("href")
                if urllib.parse.urlparse(self.base).netloc == "":
                    self.base = urllib.parse.urljoin(self.downloader.netloc, self.base)
            self.logger.debug(f"Base: {self.base}")

            # Handle the various types of references, if enabled
            if self.downloader.load_hyperlinks:
                self._handle_hyperlinks()
            if self.downloader.load_css:
                self._handle_links()
            if self.downloader.load_js:
                self._handle_scripts()
            if self.downloader.load_image:
                self._handle_images()

        # Determine the filename under which the content should be stored
        path = urllib.parse.urlparse(self.url).path
        if path.startswith("/"):
            path = path[1:]
        self.filename = os.path.join(self.downloader.target, path)
        if self.filename.endswith("/"):
            self.logger.warning(
                f"Added suffix 'index.html' because "
                f"'{self.filename}' ended with '/'!"
            )
            self.filename = os.path.join(self.filename, "index.html")

        # Determine the final content, based on the specified flags
        if self.downloader.prettify and self.soup:
            self.final_content = self.soup.prettify()
        elif self.downloader.rewrite_references and self.soup:
            self.final_content = self.soup.decode()
        else:
            self.final_content = self.response.content

        # Don't overwrite existing files if requested
        if os.path.exists(self.filename) and not self.downloader.overwrite:
            self.logger.info(f"File {self.filename} has not been written, it already exists.")
            self.written = False
            self.finished = True
            return

        # Determine the file opening mode
        if isinstance(self.final_content, str):
            mode = "w"
        elif isinstance(self.final_content, bytes):
            mode = "wb"
        else:
            self.logger.critical("content must be bytes or str")
            raise TypeError("content must be bytes or str")

        # Finally store the result in the desired file
        os.makedirs(os.path.split(self.filename)[0], exist_ok=True)
        with open(self.filename, mode) as f:
            self.logger.debug(
                f"{f.write(self.final_content)} "
                f"bytes written to {self.filename}."
            )
            self.written = True

        self.finished = True


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
        help="switch to rewrite hyperlink references to other downloaded content",
        dest="rewrite",
        action="store_true"
    )

    parser.add_argument(
        "--third-party",
        help="switch to enable download of third party resources (CSS, JS, images)",
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
    downloader = Downloader.from_namespace(namespace, logger)
    for i in range(namespace.threads):
        downloader.start_runner(f"runner{i}")

    while downloader.is_running():
        time.sleep(QUEUE_ACCESS_TIMEOUT)

    downloader.stop_all_runners()
    logger.info("Finished.")


if __name__ == "__main__":
    main(setup().parse_args())
