"""
Runners triggering parallel job executions using processors
"""

import queue
import logging
import typing

from . import processor


class Runner:
    """
    Runner built to start processors on download jobs in parallel
    """

    job_queue: queue.Queue
    """Reference to the 'queue' attribute of the 'Downloader' object"""
    queue_access_timeout: float
    """Timeout when accessing the queue in seconds"""

    logger: logging.Logger
    """Logger which will be used for logging"""
    exception: typing.Optional[Exception]
    """Exception raised while processing a job, if available"""
    crash_on_error: bool
    """Determine whether to kill this runner when a processor throws an exception"""

    # A runner's state may be one of the following five options:
    # 0 -> the runner has just been created, it's not running yet
    # 1 -> the runner is up and performing actual work
    # 2 -> the runner is doing something, but it was requested to quit
    # 3 -> the runner exited successfully
    # 4 -> the runner crashed due to an exception
    # 5 -> the runner skipped an iteration due to an empty queue (running)
    state: int
    """Current state of the runner"""

    processor_kwargs: dict
    """Dictionary of keyword arguments supplied to the processor's constructor"""

    def __init__(
            self,
            job_queue: queue.Queue,
            logger: logging.Logger,
            queue_access_timeout: float,
            crash_on_error: bool = False,
            processor_kwargs: dict = None
    ):
        self.job_queue = job_queue
        self.logger = logger
        self.queue_access_timeout = queue_access_timeout
        self.crash_on_error = crash_on_error

        self.exception = None
        self.state = 0

        self.processor_kwargs = processor_kwargs
        if processor_kwargs is None:
            self.processor_kwargs = {}

    def run(self):
        """
        Perform the actual work in a blocking loop
        """

        self.logger.debug(f"Starting runner loop ...")
        self.state = 1

        while self.state < 2 or self.state == 5:
            try:
                current_job = self.job_queue.get(True, self.queue_access_timeout)
                self.state = 1
            except queue.Empty:
                if self.state < 2:
                    self.state = 5
                continue

            try:
                worker = processor.DownloadProcessor(current_job, **self.processor_kwargs)
                if worker.run():
                    self.logger.debug(f"Worker processed {current_job} successfully.")
                else:
                    self.logger.debug(f"Processing of {current_job} failed somehow.")

                # TODO: handle derived jobs
                if len(worker.descendants) > 0:
                    self.logger.warning(f"Found {len(worker.descendants)} new derived jobs.")

                for item in set(current_job.references):
                    self.job_queue.put(item)

            except Exception as exc:
                self.exception = exc
                self.logger.error(f"Error during handling of '{current_job}'!", exc_info=True)
                if self.crash_on_error:
                    self.state = 4
                    raise

        self.state = 3