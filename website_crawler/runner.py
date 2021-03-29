"""
Runners triggering parallel job executions using processors
"""

import queue
import logging
import typing
from enum import Enum, auto as _auto

from . import processor
from .job import JobQueue


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

    job_queue: JobQueue
    """Reference to the 'queue' attribute of the 'Downloader' object"""
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
            job_queue: JobQueue,
            logger: logging.Logger,
            queue_access_timeout: float,
            crash_on_error: bool = False,
            options: dict = None
    ):
        self.job_queue = job_queue
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
                current_job = self.job_queue.get(True, self.queue_access_timeout)
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

                # TODO: handle derived jobs
                if len(worker.descendants) > 0:
                    self.logger.warning(f"Found {len(worker.descendants)} new derived jobs.")

                for reference in set(current_job.references):
                    self.job_queue.put(current_job.copy(reference))

            except Exception as exc:
                self.exception = exc
                self.logger.error(f"Error during handling of '{current_job}'!", exc_info=True)
                if self.crash_on_error:
                    self.state = RunnerState.CRASHED
                    raise

            self.job_queue.task_done()

        self.state = RunnerState.EXITED
