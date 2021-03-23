"""
TODO
"""

import os
import typing
import logging

from .job import DownloadJob


class BaseProcessor:
    """
    Base class for job processors

    This class provides convenient methods making the
    implementation of correct processors easier.
    """

    job: DownloadJob
    """Description of a job that should be processed, used in a read-write manner"""
    logger: logging.Logger
    """Processor's logger, should match the job's logger"""

    def save(self) -> bool:
        """
        Store the job's final content on disk, at the specified point

        This operation fails gracefully if
        required attributes don't exist (yet).

        :return: success of the operation
        """

        # Check that required attributes have already been set
        if self.job.local_path is None or self.job.final_content is None:
            return False

        # Ensure no existing files are overwritten if not allowed
        overwritten = False
        if os.path.exists(self.job.local_path):
            if not self.job.allow_overwrites:
                self.logger.info(
                    f"File '{self.job.local_path}' already exists, "
                    f"it will not be overwritten."
                )
                self.job.written = False
                self.job.finished = True
                return True
            if self.job.mention_overwrites:
                self.logger.info(f"Overwriting '{self.job.local_path}'.")
            overwritten = True

        # Determine the file opening mode
        if isinstance(self.job.final_content, str):
            mode = "w"
        elif isinstance(self.job.final_content, bytes):
            mode = "wb"
        else:
            self.logger.critical("content must be bytes or str")
            raise TypeError("content must be bytes or str")

        # Finally store the result in the desired file
        os.makedirs(os.path.split(self.job.local_path)[0], exist_ok=True)
        with open(self.job.local_path, mode) as f:
            self.logger.debug(
                f"{f.write(self.job.final_content)} "
                f"bytes written to {self.job.local_path}."
            )
        self.job.written = True
        self.job.overwritten = overwritten
        return True


class DownloadProcessor(BaseProcessor):
    """
    Worker class performing the actual work of processing a download job

    This 'processing' involves downloading the content from the remote
    server, analyzing it (in case of HTML data only) to retrieve other
    locations on the remote side that should be accessed, storing the
    downloaded data at some specific location on the local system
    and of course keeping track of all steps that have been done.

    :param job: description of a single download job (will also be
        accessed in read-write manner to store various flags and data)
    :param user_agent: user agent string to use for HTTP requests
    """

    descendants: typing.List[DownloadJob]
    """List of follow-up jobs in case of errors, if available"""
    _user_agent: str
    """User-agent string used to query the remote server"""

    def __init__(self, job: DownloadJob, user_agent: str):
        self.job = job
        self.logger = job.logger
        self.descendants = []
        self._user_agent = user_agent
