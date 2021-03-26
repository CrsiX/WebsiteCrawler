"""
Downloader for whole websites and all files belonging to it
"""

import os
import typing
import logging
import threading
import urllib.parse

from .job import DownloadJob, JobQueue
from .runner import Runner
from .handler import ALL_DEFAULT_HANDLER_CLASSES
from .constants import DEFAULT_USER_AGENT_STRING, DEFAULT_QUEUE_ACCESS_TIMEOUT


class Downloader:
    """
    Downloader for website content, filtering duplicates, extracting more targets

    :param website: base URI of the website which should be downloaded
    :param target: target directory where to store downloaded files
    :param logger: logger used to keep track of various events
    :param https_mode: whether to enforce or reject HTTPS connections
        (valid values are 0: don't do anything, 1: enforce HTTPS, 2: enforce HTTP;
        3: try HTTPS first, but fall back to using HTTP if errors occur; note
        that web servers might forward HTTP to HTTPS by default using 301 responses)
    :param base_ref: string for the `base` HTML tag (if it's None or an empty string,
        the `base` tag will be removed, if it exists; otherwise, the specified value
        will be used to build a new `base` tag to allow forming of relative paths)
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
    :param ascii_only: use ASCII chars in link and file names only (all other
        chars will be replaced with suitable characters or the underscore)
    :param user_agent: use a custom user agent string for HTTP(S) requests
    :param unique_filenames: use unique filenames for all files stored on disk
        (fixes problems in case files have the same name but differ in lowercase
        and uppercase or when ASCII-only filenames are requested, because the
        "unique" filename will only contain ASCII characters of course)
    :param crash_on_error: worker threads will crash when they encounter unexpected
        problems (otherwise, they would send the traceback to stdout and continue)
    :param queue_access_timeout: timeout to access the queue in seconds (higher
        values potentially decrease load but may also negatively affect speed)
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
            overwrite: bool = True,
            ascii_only: bool = False,
            user_agent: str = None,
            unique_filenames: bool = False,
            crash_on_error: bool = False,
            queue_access_timeout: float = None
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
        self.ascii_only = ascii_only
        self.user_agent = user_agent \
            if user_agent is not None else DEFAULT_USER_AGENT_STRING
        self.unique_filenames = unique_filenames
        self.crash_on_error = crash_on_error
        self.queue_access_timeout = queue_access_timeout \
            if queue_access_timeout is not None else DEFAULT_QUEUE_ACCESS_TIMEOUT

        if self.base_ref is not None:
            self.logger.warning("Feature not fully supported yet: base_ref")
            self.logger.info("The `base` tag will always be removed, if available.")
        if not self.rewrite_references and self.lowered:
            self.logger.info("Feature disabled: lowered")
            self.lowered = False
        if self.third_party:
            self.logger.warning("Feature not supported yet: third_party")
        if not self.rewrite_references and self.unique_filenames:
            self.logger.warning("Feature disabled: unique_filenames")
            self.unique_filenames = False
        if self.unique_filenames:
            self.logger.warning("Feature not supported yet: unique_filenames")

        self.netloc = urllib.parse.urlparse(self.website).netloc
        if self.netloc == "":
            self.logger.error("Empty net location! Further operation might fail.")

        if https_mode not in (0, 1, 2, 3):
            self.logger.error(f"Unknown https mode detected: {https_mode}")
            self.logger.warning("Set https mode to default value.")
            self.https_mode = 0
        elif https_mode == 3:
            self.logger.warning("Feature not supported yet: https_mode=3")
            self.logger.warning("Set https mode to default value.")
            self.https_mode = 0

        if not os.path.exists(target):
            os.makedirs(target, exist_ok=True)
            self.logger.debug("Created missing target directory.")
        elif not os.path.isdir(target):
            self.logger.critical("Target directory is no directory!")
            raise RuntimeError("Target directory is no directory!")

        self._runners = {}
        self.downloads = {}
        self.queue: JobQueue = JobQueue()

        def _ident():
            n = 0
            while True:
                yield n
                n += 1

        self._runner_ident = _ident()

        self.queue.put(DownloadJob(
            website,
            target,
            logging.getLogger("first-job"),  # should be overwritten by runner
            ALL_DEFAULT_HANDLER_CLASSES
        ))
        self.logger.debug("Initialized downloader.")

    def get_status(self) -> str:
        """
        Return a short status message containing parsable state information

        :return: comma separated string of key=value pairs
        """

        return (
            f"runners_total={len(self._runners)},"
            f"runners_dead={len(list(filter(lambda k: self._runners[k][0].state in (3, 4), self._runners)))},"
            f"downloads_total={len(self.downloads)},"
            f"downloads_okay={len(list(filter(lambda x: self.downloads[x] == 200, self.downloads)))},"
            f"downloads_doing={len(list(filter(lambda x: self.downloads[x] == 0, self.downloads)))},"
            f"queue_size={self.queue.qsize()}"
        )

    def start_new_runner(self):
        """
        Start a new runner in a separate thread
        """

        ident = next(self._runner_ident)
        runner = Runner(
            self.queue,
            logging.getLogger(f"runner{ident}"),
            self.queue_access_timeout,
            self.crash_on_error,
            {}
        )

        thread = threading.Thread(target=runner.run, daemon=False)
        self._runners[ident] = runner, thread
        self.logger.debug(f"Added runner '{ident}'.")
        thread.start()

    def stop_runner(self, key: int, timeout: int) -> bool:
        """
        Join the specified runner (which is a blocking operation)

        :param key: identification key for the runner (and suffix of its logger)
        :param timeout: max time to wait for the worker thread to finish
        :return: whether the runner was found and told to stop
        """

        if key not in self._runners:
            self.logger.warning(f"Runner '{key}' couldn't be stopped: not found.")
            return False

        self._runners[key][0].state = 2
        self._runners[key][1].join(timeout=timeout)
        return True

    def stop_all_runners(self) -> bool:
        """
        Join all runners

        This is a blocking operation. Note that this might take an infinite
        amount of time if at least one runner is not about to exit.

        :return: success of the operation (whether all runners have exited)
        """

        for key in self._runners:
            runner, thread = self._runners[key]
            if runner.state in (0, 1, 5):
                runner.state = 2
                self.logger.debug(f"Set runner state of runner '{key}' -> 2")
            elif runner.state == 3:
                self.logger.debug(f"Runner '{key}' seems to have already finished")
            elif runner.state == 4:
                self.logger.debug(f"Runner '{key}' seems to have already crashed")

        for key in self._runners:
            runner, thread = self._runners[key]
            thread.join()
            self.logger.debug(f"Stopped runner '{key}'")

        return True

    def is_running(self) -> bool:
        """
        Determine whether the workers are currently doing something

        :return: whether at least one runner is working on something
        """

        return any(map(
            lambda k: self._runners[k][0].state in (0, 1, 2),
            self._runners.keys()
        ))

    def _run(self, ident: str):
        """
        Perform the actual work in a loop

        :param ident: (hopefully) unique string for runner identification
        """

        logger = logging.getLogger(ident)
        logger.debug(f"Starting running loop for {ident} ...")
        self._runner_states[ident] = 1

        while self._runner_states[ident] < 2 or self._runner_states[ident] == 5:
            try:
                current_job = self.queue.get(True, self.queue_access_timeout)
                self._runner_states[ident] = 1
            except queue.Empty:
                if self._runner_states[ident] < 2:
                    self._runner_states[ident] = 5
                continue

            # Avoid duplicates in the queue by reserving the downloads 'slot'
            if current_job in self.downloads:
                self.logger.debug(
                    f"Ignoring queue job '{current_job}' "
                    f"(download state {self.downloads[current_job]})"
                )
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
                if self.crash_on_error:
                    self._runner_states[ident] = 4
                    raise

        self._runner_states[ident] = 3


class DownloadWorker:
    """
    Worker class performing the actual work of downloading, analyzing, storing, ...

    :param url: string or parsed URL result containing the URL that should be processed
    :param logger: the logger which should be used
    :param downloader: a reference to the Downloader object to get more details
    """

    def __init__(self, url: typing.Union[str, urllib.parse.ParseResult], logger: logging.Logger, downloader: Downloader):
        if isinstance(url, str):
            url = urllib.parse.urlparse(url)

        self.url: urllib.parse.ParseResult = url
        """URL that should be requested from the server, analyzed and stored"""
        self.logger: logging.Logger = logger
        """Logger which will be used for logging"""
        self.downloader: Downloader = downloader
        """Reference to the Downloader object to access certain attributes (read-only)"""

        self.base: typing.Optional[str] = None
        """URI as extracted and modified from the `base` HTML tag, if available"""
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

    def _get_target(self, target: str) -> typing.Optional[str]:
        """
        Transform the partly defined target string to a full URL

        The implementation of this method is partly based on RFC 3986, section 5.1 and 5.2.

        :param target: anything that seems to be an URI, relative or absolute
        :return: a full URL that can be used to request further resources,
            if possible and the target matched the criteria (otherwise None)
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

        def remove_dot_segments(p: str) -> str:
            """
            Remove the dot segments of a path `p`
            """

            if "./" in p or "/." in p:
                self.logger.warning("Feature not implemented: remove_dot_segments")
            return p

        url = urllib.parse.urlparse(target)
        scheme, netloc, path, params, query, fragment = url

        if self.base:
            base = urllib.parse.urlparse(self.base)
        else:
            base = self.url

        # Unknown schemes are ignored (e.g. mailto:) and a given schema indicates
        # an absolute URL which should not be processed (only filtered)
        if scheme != "" and scheme.lower() not in ("http", "https"):
            return
        elif scheme == "":
            if self.downloader.https_mode == 0:
                scheme = self.url.scheme
            elif self.downloader.https_mode == 1:
                scheme = "https"
            elif self.downloader.https_mode == 2:
                scheme = "http"
        elif netloc != "" and netloc.lower() == self.downloader.netloc.lower():
            return urllib.parse.urlunparse(
                (scheme, netloc, remove_dot_segments(path), params, query, "")
            )

        # Other network locations are ignored (so we don't traverse the whole web)
        if netloc != "" and netloc.lower() != self.downloader.netloc.lower():
            return
        elif netloc != "":
            return urllib.parse.urlunparse(
                (scheme, netloc, remove_dot_segments(path), params, query, "")
            )

        netloc = self.downloader.netloc

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

    def _get_relative_path(self, ref: str) -> str:
        """
        Get the relative path pointing from the current file towards `ref`

        :param ref: any kind of reference, but works best for absolute URLs
            (therefore, one should better call `_get_target` on it first)
        :return: relative path pointing from the current file towards the reference
        """

        path = urllib.parse.urlparse(ref).path
        if self.downloader.ascii_only:
            path = helper.convert_to_ascii_only(
                path,
                helper.SMALL_ASCII_CONVERSION_TABLE
            )
        if self.downloader.lowered:
            path = path.lower()
        return path

    def _handle_specific_tag(
            self,
            tag_type: str,
            attr_name: str,
            filter_function: typing.Callable[[bs4.element.Tag], bool] = lambda x: True
    ):
        """
        Handle all tags of a specific type using one of its attributes

        This method extracts the URLs found in all tags of the specified type,
        provided the name of the attribute where the URL will be found is
        present as well. If rewriting of references had been enabled, this step
        will also be done in this method. Use the filter function to restrict
        the range of scanned and processed tags in the input file.

        :param tag_type: type of HTML tag (e.g. `a` or `img`)
        :param attr_name: attribute name for that tag (e.g. `href` or `src`)
        :param filter_function: function which accepts exactly one parameter,
            one single HTML tag, and determines whether this tag should be analyzed
            (filtering and processing of URLs takes place after this filter, so
            one doesn't need to care about e.g. schemes or other network locations)
        """

        for tag in self.soup.find_all(tag_type):
            if tag.has_attr(attr_name) and filter_function(tag):
                target = self._get_target(tag.get(attr_name))
                if target is not None:
                    self.logger.debug(f"New reference: {target}")
                    self.references.add(target)
                    tag.attrs[attr_name] = self._get_relative_path(target)

    def _handle_hyperlinks(self):
        """
        Handle all `a` tags occurring in the file (represented as soup)

        This method extracts the URLs of all hyperlink references of `a` tags
        and adds them to the set of references if it matches the criteria. If
        rewriting of references had been enabled, this step will also be done here.
        """

        self._handle_specific_tag("a", "href")

    def _handle_links(self):
        """
        Handle all `link` tags occurring in the file (represented as soup)

        This method extracts the URLs of all external resources mentioned in `link`
        tags and adds them to the set of references if it matches the criteria. If
        rewriting of references had been enabled, this step will also be done here.
        """

        def filter_func(tag: bs4.element.Tag) -> bool:
            if tag.has_attr("rel"):
                is_css = "stylesheet" in tag.get("rel")
                enabled = not tag.has_attr("disabled")
                if self.downloader.load_css and is_css and enabled:
                    return True
            return False

        self._handle_specific_tag("link", "href", filter_func)

    def _handle_scripts(self):
        """
        Handle all `script` tags occurring in the file (represented as soup)

        This method extracts the URLs of all external resources mentioned in `script`
        tags and adds them to the set of references if it matches the criteria. If
        rewriting of references had been enabled, this step will also be done here.
        """

        self._handle_specific_tag("script", "src")

    def _handle_images(self):
        """
        Handle all `img` tags occurring in the file (represented as soup)

        This method extracts the URLs of all external resources mentioned in `img`
        tags and adds them to the set of references if it matches the criteria. If
        rewriting of references had been enabled, this step will also be done here.
        """

        self._handle_specific_tag("img", "src")

    def run(self):
        """
        Perform the actual work as a blocking process
        """

        # Restrict multiple (unintentional) calls to this method
        if self.started or self.finished:
            return
        self.started = True

        self.logger.debug(f"Currently processing: {self.url.geturl()}")
        self.response = requests.get(
            self.url.geturl(),
            headers={"User-Agent": self.downloader.user_agent}
        )
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
            if self.soup.base is not None and self.soup.base.has_attr("href"):
                self.base = self.soup.base.get("href")
                if urllib.parse.urlparse(self.base).netloc == "":
                    self.base = urllib.parse.urljoin(self.downloader.netloc, self.base)
            self.logger.debug(f"Base: {self.base}")

            # Remove all `base` tags
            while self.soup.base:
                self.logger.debug("Removing (one of) the `base` tag(s)")
                self.soup.base.replace_with("")

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
        path = self.url.path
        if self.downloader.ascii_only:
            path = helper.convert_to_ascii_only(path, helper.SMALL_ASCII_CONVERSION_TABLE)
        if self.downloader.lowered:
            path = path.lower()
        if path.startswith("/"):
            path = path[1:]
        if len(path) == "":
            self.logger.warning("Empty path detected. Added 'index.html'!")
            path = "index.html"
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
