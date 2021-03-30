"""
Runners triggering parallel job executions using processors
"""

import queue
import typing
import logging
from enum import Enum, auto as _auto

from . import processor
from .job import JobManager


class RunnerState(Enum):
    CREATED = _auto()  # the runner has just been created
    WORKING = _auto()  # the runner processes jobs
    WAITING = _auto()  # the runner waits for new jobs to be available
    ENDING = _auto()   # the runner processes its last job
    EXITED = _auto()   # the runner exited gracefully
    CRASHED = _auto()  # the runner crashed due to unhandled exception


class Runner:
    """
    Runner built to start processors on download jobs in parallel
    """

    job_manager: JobManager
    """Reference to the ``JobManager`` instance used by the ``Downloader`` object"""
    queue_access_timeout: float
    """Timeout when accessing the queue in seconds"""

    logger: logging.Logger
    """Logger which will be used for logging"""
    exception: typing.Optional[Exception]
    """Exception raised while processing a job, if available"""
    crash_on_error: bool
    """Determine whether to kill this runner when a processor throws an exception"""

    state: RunnerState
    """Current state of the runner"""

    options: dict
    """Dictionary of keyword arguments supplied to processors and handlers"""

    def __init__(
            self,
            job_manager: JobManager,
            logger: logging.Logger,
            queue_access_timeout: float,
            crash_on_error: bool = False,
            options: dict = None
    ):
        self.job_manager = job_manager
        self.logger = logger
        self.queue_access_timeout = queue_access_timeout
        self.crash_on_error = crash_on_error

        self.exception = None
        self.state = RunnerState.CREATED

        self.options = options
        if options is None:
            self.options = {}

    def run(self):
        """
        Perform the actual work in a blocking loop
        """

        self.logger.debug(f"Starting runner loop ...")
        self.state = RunnerState.WORKING

        while self.state in (RunnerState.WORKING, RunnerState.WAITING):
            try:
                current_job = self.job_manager.get(self.queue_access_timeout)
                self.state = RunnerState.WORKING
            except queue.Empty:
                if self.state == RunnerState.WORKING:
                    self.state = RunnerState.WAITING
                continue

            current_job.logger = self.logger

            try:
                worker = processor.DownloadProcessor(current_job, self.options)
                if worker.run():
                    self.logger.debug(f"Worker processed {current_job} successfully.")
                else:
                    self.logger.warning(f"Processing of {current_job} failed somehow.")

                if len(worker.descendants) > 0:
                    self.logger.warning(f"Found {len(worker.descendants)} new derived jobs.")
                for job in worker.descendants:
                    self.job_manager.put(job)

                for reference in set(current_job.references):
                    self.job_manager.put(current_job.copy(reference))

            except Exception as exc:
                self.exception = exc
                self.logger.error(f"Error during handling of '{current_job}'!", exc_info=True)
                if self.crash_on_error:
                    self.state = RunnerState.CRASHED
                    raise

            finally:
                self.job_manager.complete(current_job)

        self.state = RunnerState.EXITED
