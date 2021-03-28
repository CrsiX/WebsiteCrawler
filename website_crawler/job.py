"""
Description of a single job
"""

import os
import queue
import typing
import logging
import urllib.parse

# import bs4
import requests

from .handler import BaseContentHandler
from .constants import DEFAULT_USER_AGENT_STRING


class DownloadJob:
    """
    Description of a single 'download job'

    Instances of this class should be treated as a 'better'
    kind of dictionary as they also contain type annotations
    and descriptions of the attributes. After all, instances
    of this class are meant to just store data and references.
    """

    __slots__ = (
        "remote_path",
        "remote_url",
        "netloc",
        "response",
        "response_code",
        "response_type",
        "handler",
        "references",
        # "soup",
        "local_base",
        "local_path",
        "final_content",
        "https_mode",
        "user_agent",
        "prettify",
        "allow_rewrites",
        "allow_overwrites",
        "mention_overwrites",
        "started",
        "delayed",
        "analyzed",
        "written",
        "overwritten",
        "finished",
        "logger",
        "exception"
    )

    # Information about the remote side
    remote_path: str
    """Remote absolute path (URL) to the file that should be downloaded"""
    remote_url: urllib.parse.ParseResult
    """URL that should be requested from the server, analyzed and stored"""
    netloc: str
    """Remote network location name used to restrict queries to the 'first' party"""

    # Information about the response from the remote web server
    response: typing.Optional[requests.Response]
    """Response of the web server, answering the request for the URL, if available"""
    response_code: typing.Optional[int]
    """HTTP response status code of the request, if available"""
    response_type: typing.Optional[str]
    """Value of the HTTP header field 'Content-Type', if available"""

    # Information about the state of the processing (specifically the content handling)
    handler: typing.List[typing.Type[BaseContentHandler]]
    """Collection of analyzers/handlers of the content, identified by the mime type"""
    references: typing.Set[str]
    """Storage of references found in the analyzed response, grouped by type of analyzer"""
    # soup: typing.Optional[bs4.BeautifulSoup]
    # """BeautifulSoup object containing the tree of the HTML response, if available"""

    # Information about the local side
    local_base: str
    """Local base directory where to store all downloaded files (root of the hierarchy)"""
    local_path: typing.Optional[str]
    """Local path where the file has been stored, if available"""
    final_content: typing.Union[bytes, str, None]
    """Final version of the content as stored in the target file, if available"""

    # Various options that change the behavior of the processing unit(s)
    https_mode: int
    """Mode affecting the use of HTTPS, see the description in the Downloader class"""
    user_agent: str
    """User-agent string as sent in the HTTP header to query the remote side"""
    prettify: bool
    """Determine whether to 'prettify' the resulting output (HTML data only)"""
    allow_rewrites: bool
    """Allow rewriting of references to other downloaded files (HTML data only)"""
    allow_overwrites: bool
    """Allow overwriting existing local files without further asking"""
    mention_overwrites: bool
    """Determine whether to mention overwriting files using log level INFO"""

    # Various status flags (may become 'True' in roughly this order)
    started: bool
    """Info whether the processing of the URL has been started"""
    delayed: bool
    """Info whether the response processing has been delayed because of errors"""
    analyzed: bool
    """Info whether the response was handled as HTML result"""
    written: bool
    """Info whether the content has been written to the desired filename"""
    overwritten: bool
    """Info whether another file at the local path had been overwritten"""
    finished: bool
    """Info whether the processing of the URL has been finished"""

    # Generic common stuff
    logger: logging.Logger
    """Logger which will be used for logging"""
    exception: typing.Optional[Exception]
    """Exception that occurred during the handling of the job, if available"""

    def __init__(
            self,
            remote: typing.Union[str, urllib.parse.ParseResult],
            local_base: str,
            logger: logging.Logger,
            handler: typing.List[typing.Type[BaseContentHandler]],
            **kwargs
    ):

        if isinstance(remote, str):
            self.remote_path = remote
            self.remote_url = urllib.parse.urlparse(self.remote_path)
        elif isinstance(remote, urllib.parse.ParseResult):
            self.remote_url = remote
            self.remote_path = self.remote_url.geturl()
        else:
            raise TypeError(f"'remote' has type {type(remote)}")

        if self.remote_url.netloc == "":
            raise ValueError(f"No absolute URL: '{self.remote_path}'")

        if not os.path.exists(local_base) or not os.path.isdir(local_base):
            raise ValueError(f"No directory or doesn't exist: {local_base}")

        self.netloc = self.remote_url.netloc

        self.response = None
        self.response_code = None
        self.response_type = None

        self.handler = handler
        self.references = set()
        # self.soup = None

        self.local_base = local_base
        self.local_path = None
        self.final_content = None

        self.https_mode = 0
        self.user_agent = DEFAULT_USER_AGENT_STRING
        self.prettify = False
        self.allow_rewrites = True
        self.allow_overwrites = True
        self.mention_overwrites = False

        self.started = False
        self.delayed = False
        self.analyzed = False
        self.written = False
        self.overwritten = False
        self.finished = False

        self.logger = logger
        self.exception = None

        for k, v in kwargs.items():
            if k in self.__slots__ and not k.startswith("remote"):
                setattr(self, k, v)

    def __repr__(self) -> str:
        if self.response_code is None:
            return f"DownloadJob<{self.remote_path}>()"
        return f"DownloadJob<{self.remote_path}>({self.response_code})"

    def copy(self, remote: typing.Union[str, urllib.parse.ParseResult, None] = None):
        """
        Create a copy of self, possibly replacing the remote endpoint

        Note that this copy is a *new* job, i.e. no progress will be copied.

        :param remote: optional new endpoint of the new job
        """

        if remote is None:
            remote = self.remote_url

        return DownloadJob(
            remote,
            self.local_base,
            self.logger,
            self.handler.copy()
        )


class JobQueue(queue.Queue):
    """
    FIFO queue keeping track of download jobs

    Note that the only difference between this queue and
    the default queue (its superclass) is the type of
    objects that should be managed by an instance of it.
    """

    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize)

    def get(self, block: bool = True, timeout: float = None) -> DownloadJob:
        """
        Remove and return an item from the queue

        Works exactly like the default get() call but
        adds type annotations for the returned value.
        """

        return super().get(block, timeout)

    def put(self, item: DownloadJob, block: bool = True, timeout: float = None):
        """
        Put an item into the queue

        Works exactly like the default put() call but
        with an additional type check of the inserted item.
        """

        if not isinstance(item, DownloadJob):
            raise TypeError(f"Expected DownloadJob, but got {type(item)}")

        return super().put(item, block, timeout)
