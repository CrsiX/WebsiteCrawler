"""
Description of a single job
"""

import typing
import logging
import urllib.parse

import bs4
import requests


class DownloadJob:
    """
    Description of a single 'download job'

    Instances of this class should be treated as a 'better'
    kind of dictionary as they also contain type annotations
    and descriptions of the attributes. After all, instances
    of this class are meant to just store data and references.
    """

    # Information about the remote side
    remote_path: str
    """Remote absolute path (URL) to the file that should be downloaded"""
    remote_url: urllib.parse.ParseResult
    """URL that should be requested from the server, analyzed and stored"""
    netloc: str
    """Remote network location name used to restrict queries to the 'first' party"""

    # Information about the response from the remote web server
    response: typing.Optional[requests.Response] = None
    """Response of the web server, answering the request for the URL, if available"""
    response_code: typing.Optional[int] = None
    """HTTP response status code of the request, if available"""
    response_type: typing.Optional[str] = None
    """Value of the HTTP header field 'Content-Type'"""

    # Information about the state of the processing (specifically the content analyze)
    analyzer: typing.Dict[str, typing.Callable]  # TODO: precise -> signature of callable
    """Collection of analyzers of the HTML content, identified by a name"""
    references: typing.Dict[str, typing.Set[str]]
    """Storage of references found in the analyzed response, grouped by type of analyzer"""
    soup: typing.Optional[bs4.BeautifulSoup] = None
    """BeautifulSoup object containing the tree of the HTML response, if available"""

    # Information about the local side
    local_base: str
    """Local base directory where to store all downloaded files (root of the hierarchy)"""
    local_path: typing.Optional[str] = None
    """Local path where the file has been stored, if available"""
    final_content: typing.Union[bytes, str, None] = None
    """Final version of the content as stored in the target file, if available"""

    # Various options that change the behavior of the processing unit(s)
    https_mode: int
    """Mode affecting the use of HTTPS, see the description in the Downloader class"""
    prettify: bool
    """Determine whether to 'prettify' the resulting output (HTML data only)"""
    allow_rewrites: bool
    """Allow rewriting of references to other downloaded files (HTML data only)"""
    allow_overwrites: bool
    """Allow overwriting existing local files without further asking"""
    mention_overwrites: bool
    """Determine whether to mention overwriting files using log level INFO"""

    # Various status flags (may become 'True' in roughly this order)
    started: bool = False
    """Info whether the processing of the URL has been started"""
    delayed: bool = False
    """Info whether the response processing has been delayed because of errors"""
    analyzed: bool = False
    """Info whether the response was handled as HTML result"""
    written: bool = False
    """Info whether the content has been written to the desired filename"""
    overwritten: bool = False
    """Info whether another file at the local path had been overwritten"""
    finished: bool = False
    """Info whether the processing of the URL has been finished"""

    # Generic common stuff
    logger: logging.Logger
    """Logger which will be used for logging"""
    exception: typing.Optional[Exception] = None
    """Exception that occurred during the handling of the job, if available"""
