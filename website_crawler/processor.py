"""
TODO
"""

import typing
import logging

from .job import DownloadJob


class DownloadProcessor:
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

    job: DownloadJob
    """Description of a job that should be processed, used in a read-write manner"""
    logger: logging.Logger
    """Processor's logger, should match the job's logger"""
    descendants: typing.List[DownloadJob]
    """List of follow-up jobs in case of errors, if available"""
    _user_agent: str
    """User-agent string used to query the remote server"""

    def __init__(self, job: DownloadJob, user_agent: str):
        self.job = job
        self.logger = job.logger
        self.descendants = []
        self._user_agent = user_agent
