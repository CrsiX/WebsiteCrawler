"""
Runners triggering parallel job executions using processors
"""

import queue
import typing
import logging

from . import (
    job as _job,
    processor as _processor
)
from .constants import RunnerState


class Runner:
    """
    Runner built to start processors on download jobs in parallel
    """

    job_manager: _job.JobManager
    """Reference to the ``JobManager`` instance used by the ``Downloader`` object"""
    queue_access_timeout: float
    """Timeout when accessing the queue in seconds"""

    logger: logging.Logger
    """Logger which will be used for logging"""
    exception: typing.Optional[Exception]
    """Exception raised while processing a job, if available"""
    crash_on_error: bool
    """Determine whether to kill this runner when a processor throws an exception"""
    quit_on_empty_queue: bool
    """Determine whether to quit the runner loop when the queue becomes empty"""

    state: RunnerState
    """Current state of the runner"""

    def __init__(
            self,
            job_manager: _job.JobManager,
            logger: logging.Logger,
            queue_access_timeout: float,
            crash_on_error: bool = False,
            quit_on_empty_queue: bool = False
    ):
        self.job_manager = job_manager
        self.logger = logger
        self.queue_access_timeout = queue_access_timeout
        self.crash_on_error = crash_on_error
        self.quit_on_empty_queue = quit_on_empty_queue

        self.exception = None
        self.state = RunnerState.CREATED

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
                if self.quit_on_empty_queue:
                    self.state = RunnerState.ENDING
                continue

            current_job.logger = self.logger

            try:
                worker = _processor.DownloadProcessor(current_job)
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
