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


# Better don't try to actively use this class,
# it only provides some attribute annotations
# and a constructor for the derived classes below.
class _BaseDownloader:
    """
    :param website: base URI of the website which should be downloaded
    :param target_directory: target directory where to store downloaded files
    :param logger: logger used to keep track of various events
    :param crash_on_error: worker threads will crash when they encounter unexpected
        problems (otherwise, they would send the traceback to stdout and continue)
    :param queue_access_timeout: timeout to access the queue in seconds (higher
        values potentially decrease load but may also negatively affect speed)
    :param manager_debug_mode: whether to store the full download job in the
        history or just the HTTP response code (heavily increased memory usage)
    """

    jobs: JobManager
    logger: logging.Logger
    website: str

    _options: typing.Dict[str, typing.Any]
    _crash_on_error: bool
    _queue_access_timeout: float

    def __init__(
            self,
            website: str,
            target_directory: str,
            logger: logging.Logger,
            crash_on_error: bool = DEFAULT_RUNNER_CRASH_ON_ERROR,
            queue_access_timeout: float = DEFAULT_QUEUE_ACCESS_TIMEOUT,
            manager_debug_mode: bool = DEFAULT_JOB_MANAGER_FULL_MODE,
            **kwargs
    ):
        self.website = website
        self.logger = logger

        self._options = kwargs
        self._crash_on_error = crash_on_error
        self._queue_access_timeout = queue_access_timeout

        if urllib.parse.urlparse(self.website).netloc == "":
            self.logger.error("Empty network location! Further operation might fail.")

        if not os.path.exists(target_directory):
            os.makedirs(target_directory, exist_ok=True)
            self.logger.debug("Created missing target directory.")
        elif not os.path.isdir(target_directory):
            self.logger.critical("Target directory is no directory!")
            raise RuntimeError("Target directory is no directory!")

        self.jobs = JobManager(manager_debug_mode)
        self.jobs.put(DownloadJob(
            website,
            target_directory,
            logging.getLogger("first-job"),  # should be overwritten by runner
            ALL_DEFAULT_HANDLER_CLASSES
        ))

    # A subclass should implement this method, depending on
    # the exact handling of the runner(s) used by the class.
    def run(self, **kwargs) -> bool:
        raise NotImplementedError


class SingleThreadedDownloader(_BaseDownloader):
    __doc__ = """
    Downloader for linked website content

    This class provides a convenient control wrapper around
    runners, processors and analyzers. It was designed to be
    used in a single-threaded environment and works using
    a single blocking process. This allows for easier debugging
    and improves performance for very small websites, but it
    might not be the tool you were looking for, especially for
    larger sites with dozens of resources or slow remote servers.
    """ + _BaseDownloader.__doc__

    def run(self, **kwargs) -> bool:
        """
        Start the runner to download all content and wait for it to finish

        This is a blocking method call. It may take a lot
        of time for the method to finish operation properly.

        :param kwargs: keyword arguments are silently **ignored**
        :return: success of the operation
        """

        runner = Runner(
            self.jobs,
            logging.getLogger("runner"),
            self._queue_access_timeout,
            self._crash_on_error,
            True,
            self._options
        )
        self.logger.debug("Starting runner...")
        runner.run()
        return True


class MultiThreadedDownloader(_BaseDownloader):
    __doc__ = """
    Downloader for linked website content

    This class provides a convenient control wrapper around
    runners, processors and analyzers. It was designed to be
    used in a multi-threaded environment. If you want a single
    blocking process, use the ``SingleThreadedDownloader``
    class instead. Note, however, that certain runner control
    methods are not present in that class. The provided
    ``run()`` method might be used if you don't care about
    the exact handling of the runners and just want to get
    your job done instead. Note that that's yet another
    blocking process (but you may use it in your main thread).
    """ + _BaseDownloader.__doc__

    _runners: typing.Dict[int, typing.Tuple[Runner, threading.Thread]]
    _runners_ident: typing.Generator

    def __init__(
            self,
            website: str,
            target_directory: str,
            logger: logging.Logger,
            crash_on_error: bool = DEFAULT_RUNNER_CRASH_ON_ERROR,
            queue_access_timeout: float = DEFAULT_QUEUE_ACCESS_TIMEOUT,
            manager_debug_mode: bool = DEFAULT_JOB_MANAGER_FULL_MODE,
            **kwargs
    ):
        super().__init__(
            website,
            target_directory,
            logger,
            crash_on_error,
            queue_access_timeout,
            manager_debug_mode,
            **kwargs
        )

        def _ident():
            n = 0
            while True:
                yield n
                n += 1

        self._runners: typing.Dict[int, typing.Tuple[Runner, threading.Thread]] = {}
        self._runner_ident: typing.Generator = _ident()

    def run(
            self,
            threads: int = DEFAULT_DOWNLOADER_THREAD_COUNT,
            status: typing.Tuple[float, typing.Callable[[str], None]] = None,
            **kwargs
    ) -> bool:
        """
        Start <threads> runners and wait for it to finish

        This is a blocking method call. It may take a lot
        of time for the method to finish operation properly.
        You don't have to use this method, as it will only
        handle adding the runners and waiting for them to
        finish their operation. It allows to send status
        updates periodically, see the ``status`` parameter.

        :param threads: number of runners that should be started
        :param status: tuple of a float representing the time between
            status updates and a function that collects the formatted
            status information (e.g. ``print`` or ``logger.debug``);
            the updates may be disabled using ``None``, an "empty"
            collector function or a sleep time less or equal to zero
        :param kwargs: other keyword arguments are silently **ignored**
        :return: success of the operation
        """

        do_status_updates = threading.Lock()
        do_status_updates.acquire()

        def handle_status():
            while not do_status_updates.acquire(timeout=status[0]):
                status[1](self.get_status())
            do_status_updates.release()

        update_thread = None
        if status is not None and status[0] > 0:
            update_thread = threading.Thread(target=handle_status, daemon=True)
            update_thread.start()

        for _ in range(threads):
            self.start_new_runner()

        while self.is_running():
            self.jobs.join()

        self.stop_all_runners()
        do_status_updates.release()
        if update_thread is not None:
            update_thread.join()
        self.logger.info("Finished.")

        return True

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
            f"jobs_completed={self.jobs.completed},"
            f"jobs_succeeded={self.jobs.succeeded},"
            f"jobs_reserved={self.jobs.reserved},"
            f"jobs_pending={self.jobs.pending}"
        )

    def start_new_runner(self):
        """
        Start a new runner in a separate thread
        """

        ident = next(self._runner_ident)
        runner = Runner(
            self.jobs,
            logging.getLogger(f"runner{ident}"),
            self._queue_access_timeout,
            self._crash_on_error,
            False,
            self._options
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
                RunnerState.ENDING
            ),
            self._runners.keys()
        ))


DefaultDownloader = MultiThreadedDownloader
