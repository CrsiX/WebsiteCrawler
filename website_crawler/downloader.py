"""
Downloader for whole websites and all files belonging to it
"""

import os
import typing
import logging
import threading
import urllib.parse

from .job import DownloadJob, JobManager
from .runner import Runner, RunnerState
from .handler import ALL_DEFAULT_HANDLER_CLASSES
from .constants import *


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
            https_mode: int = DEFAULT_HTTPS_MODE,
            base_ref: typing.Optional[str] = None,
            load_hyperlinks: bool = DEFAULT_INCLUDE_HYPERLINKS,
            load_css: bool = DEFAULT_INCLUDE_STYLESHEETS,
            load_js: bool = DEFAULT_INCLUDE_JAVASCRIPT,
            load_image: bool = DEFAULT_INCLUDE_IMAGES,
            rewrite_references: bool = DEFAULT_REWRITE_REFERENCES,
            lowered: bool = DEFAULT_LOWERED_PATHS,
            third_party: bool = DEFAULT_LOAD_THIRD_PARTY_RESOURCE,
            prettify: bool = DEFAULT_HTML_OUTPUT_PRETTIFIED,
            overwrite: bool = DEFAULT_ALLOW_OVERWRITING_FILES,
            ascii_only: bool = DEFAULT_ASCII_ONLY_REFERENCES,
            user_agent: str = DEFAULT_USER_AGENT_STRING,
            unique_filenames: bool = DEFAULT_UNIQUE_FILENAMES,
            crash_on_error: bool = DEFAULT_RUNNER_CRASH_ON_ERROR,
            queue_access_timeout: float = DEFAULT_QUEUE_ACCESS_TIMEOUT,
            manager_debug_mode: bool = DEFAULT_JOB_MANAGER_FULL_MODE,
            **kwargs
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
        self.user_agent = user_agent
        self.unique_filenames = unique_filenames
        self.crash_on_error = crash_on_error
        self.queue_access_timeout = queue_access_timeout

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

        self.jobs: JobManager = JobManager(manager_debug_mode)

        def _ident():
            n = 0
            while True:
                yield n
                n += 1

        self._runners: typing.Dict[int, typing.Tuple[Runner, threading.Thread]] = {}
        self._runner_ident: typing.Generator = _ident()

        self.jobs.put(DownloadJob(
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

        dead_runners = len(list(filter(
            lambda k: self._runners[k][0].state in (RunnerState.EXITED, RunnerState.CRASHED),
            self._runners
        )))

        return (
            f"runners_total={len(self._runners)},"
            f"runners_dead={dead_runners},"
            f"completed_jobs={self.jobs.completed},"
            f"successful_jobs={self.jobs.succeeded},"
            f"reserved_jobs={self.jobs.reserved}"
            f"pending_jobs={self.jobs.pending}"
        )

    def start_new_runner(self):
        """
        Start a new runner in a separate thread
        """

        ident = next(self._runner_ident)
        runner = Runner(
            self.jobs,
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

        runner, thread = self._runners[key]
        if runner.state in (RunnerState.CREATED, RunnerState.WORKING, RunnerState.WAITING):
            runner.state = RunnerState.ENDING
        thread.join(timeout=timeout)
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
            if runner.state in (RunnerState.CREATED, RunnerState.WORKING, RunnerState.WAITING):
                runner.state = RunnerState.ENDING
                self.logger.debug(f"Set runner state of runner '{key}' -> ENDING")
            elif runner.state == RunnerState.EXITED:
                self.logger.debug(f"Runner '{key}' seems to have already finished")
            elif runner.state == RunnerState.CRASHED:
                self.logger.debug(f"Runner '{key}' seems to have already crashed")
                if runner.exception is not None:
                    self.logger.warning(f"{runner.exception} caused the crash")

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
            lambda k: self._runners[k][0].state in (
                RunnerState.CREATED,
                RunnerState.WORKING,
                RunnerState.WAITING,
                RunnerState.ENDING
            ),
            self._runners.keys()
        ))
