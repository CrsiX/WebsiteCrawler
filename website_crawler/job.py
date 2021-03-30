"""
Module containing the description of a single
job and a manager to handle its states
"""

import os
import json
import queue
import typing
import _thread
import logging
import urllib.parse

import requests

from .handler import BaseContentHandler as _BaseContentHandler
from .constants import (
    DEFAULT_ACCEPTED_RESPONSE_CODES,
    DEFAULT_JOB_MANAGER_FULL_MODE,
    DEFAULT_USER_AGENT_STRING
)


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
    handler: typing.List[typing.Type[_BaseContentHandler]]
    """Collection of analyzers/handlers of the content, identified by the mime type"""
    references: typing.Set[str]
    """Storage of referenced remote resources found in the analyzed response"""

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
            handler: typing.List[typing.Type[_BaseContentHandler]],
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

    def __eq__(self, other) -> bool:
        if not isinstance(other, type(self)):
            return NotImplemented
        return self.remote_url._replace(fragment="") == other.remote_url._replace(fragment="")

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


class JobManager:
    """
    Pool storage and manager for all download jobs

    An instance holds a standard FIFO queue for all pending
    jobs, a list of currently 'reserved' slots which represent
    the downloads currently in progress and a dictionary with
    all results so far. The dictionary uses the remote URLs
    (strings) as its keys and the values are either the HTTP
    response codes for the remote URLs or the 'full' instance
    of the DownloadJob. Which one of those values is used will
    be determined at object initialization, using the boolean
    parameter ``full`` to enable the storage of the DownloadJob.
    Note that this might significantly increase memory usage
    because a successful DownloadJob always caries the whole
    final content that was also written to disk. You're better
    off using this feature for debugging purposes only.

    All methods make use of a instance-wide mutex to enable
    thread-safe operations on the data. Note that this means
    that a thread B may block until the mutex is released by
    another thread A. This might only impact for really large
    pools where a single operation takes significant time.

    The typical workflow for interacting with this manager is
    first adding new jobs to the pending queue using ``put()``.
    Some time afterwards, a call to ``get()`` pops the job
    that was inserted first (FIFO) and marks the remote URL
    represented by the job as 'reserved'. Note that both
    ``put`` and ``get`` work as you would expect from a normal
    queue, e.g. the Empty exception may be thrown and it's
    possible to specify explicit timeouts (always blocking mode).

    A call to ``check()`` determines whether a given job is
    already pending (in the queue), reserved (in the list) or
    completed (in the dict). Remote URLs are also possible here.

    After performing the work of processing a download job,
    a runner should call the ``complete()`` method using the
    job or its remote URL and the response code as argument(s).
    This ensures proper handling of future downloads and
    avoids duplicate downloads of identical resources.

    An instance furthermore provides some read-only properties:
     *  ``pending`` is the **estimated** number of pending jobs
     *  ``reserved`` is the number of reserved slots
     *  ``completed`` is the number of completed downloads,
        regardless of success of failure
     *  ``succeeded`` is the number of successful downloads only

    :param full: determine whether to store full download jobs
        in the storage dictionary or just the response code
        (also applies to the list of reserved slots)
    :param successful: list of HTTP response codes that are
        considered 'successfully' completed (uses the default
        DEFAULT_ACCEPTED_RESPONSE_CODES list if None)
    """

    _full: bool
    _lock: _thread.LockType
    _queue: JobQueue
    _storage: typing.Dict[str, typing.Union[int, DownloadJob]]
    _reserved: typing.List[typing.Union[str, DownloadJob]]
    _successful: typing.List[int]

    def __init__(
            self,
            full: bool = DEFAULT_JOB_MANAGER_FULL_MODE,
            successful: typing.List[int] = None
    ):
        self._full = full
        self._lock = _thread.allocate_lock()
        self._queue = JobQueue()
        self._storage = {}
        self._reserved = []
        self._successful = successful
        if successful is None:
            self._successful = DEFAULT_ACCEPTED_RESPONSE_CODES

    def check(self, item: typing.Union[str, DownloadJob]) -> bool:
        """
        Check whether a URL or download job has not been reserved or processed yet
        """

        with self._lock:
            if self._full:
                reserved_contains = item in self._reserved
                storage_contains = item in self._storage.values()
            else:
                reserved_contains = item.remote_path in self._reserved
                storage_contains = item.remote_path in self._storage.keys()
            return not reserved_contains and not storage_contains

    def put(self, item: DownloadJob, timeout: float = None):
        """
        Put a new download job into the queue of pending jobs

        It's ensured that the new download job wasn't already processed.
        However, the pending queue might contain duplicate jobs.
        The method uses a blocking call to the underlying queue object.

        :param item: new download job that should be added to the queue
        :param timeout: optional timeout for the queue operation
        :raises TypeError: if no DownloadJob instance was given as item
        """

        if not isinstance(item, DownloadJob):
            raise TypeError(f"Expected DownloadJob, but got {type(item)}")

        if self.check(item):
            with self._lock:
                return self._queue.put(item, True, timeout)

    def get(self, timeout: float = None) -> DownloadJob:
        """
        Remove and return a job from the queue, marking it 'reserved'

        :param timeout: optional timeout for the queue operation
        :raises queue.Empty: if the queue of pending jobs is empty
        """

        with self._lock:
            item = self._queue.get(True, timeout)
            if self._full:
                self._reserved.append(item)
            else:
                self._reserved.append(item.remote_path)
            return item

    def complete(self, item: typing.Union[str, DownloadJob], value: int = None):
        """
        Mark a previously reserved job or URL as processed

        :param item: job or remote URL that has been processed
        :param value: HTTP response code for the job (ignored for items
            of type DownloadJob, required for items of type str)
        :raises ValueError: when no value is present for an item of type str
        """

        if isinstance(item, str) and not isinstance(value, int):
            raise ValueError("Value required for items of type str")
        if self._full and not isinstance(item, DownloadJob):
            raise TypeError("Item must be type DownloadJob for 'full' storage mode")

        with self._lock:
            if item in self._reserved:
                self._reserved.remove(item)
            if isinstance(item, DownloadJob):
                if self._full:
                    self._storage[item.remote_path] = item
                else:
                    self._storage[item.remote_path] = item.response_code
            else:
                self._storage[item] = value
            self._queue.task_done()

    @property
    def pending(self) -> int:
        """
        Get the estimated number of pending jobs in the queue
        """

        return self._queue.qsize()

    @property
    def reserved(self) -> int:
        """
        Get the number of reserved 'slots'
        """

        with self._lock:
            return len(self._reserved)

    @property
    def completed(self) -> int:
        """
        Get the number of completed downloads, regardless of success
        """

        with self._lock:
            return len(self._storage)

    @property
    def succeeded(self) -> int:
        """
        Get the number of successfully completed downloads
        """

        with self._lock:
            return len(list(filter(
                lambda k: self._storage[k] in self._successful,
                self._storage.keys()
            )))


    def dumps(self, **kwargs) -> str:
        """
        Serialize the whole manager to a JSON-formatted string

        This method passes all keyword arguments to ``json.dumps``!
        """

        with self._lock:
            try:
                pending = list(self._queue.queue)
            except TypeError:
                pending = []
                try:
                    while True:
                        pending.append(self._queue.get())
                except queue.Empty:
                    pass
                for job in pending:
                    self._queue.put(job)
                    self._queue.task_done()
            pending = list(map(lambda j: j.remote_path, pending))

            completed = self._storage
            if self._full:
                completed = {k: self._storage[k].response_code for k in self._storage}

            return json.dumps(
                {
                    "pending": pending,
                    "reserved": self._reserved,
                    "completed": completed
                },
                **kwargs
            )
