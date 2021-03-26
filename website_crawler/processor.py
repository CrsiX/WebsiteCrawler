"""
TODO
"""

import os
import typing
import logging
import urllib.parse

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

    def find_absolute_target(
            self,
            target: str,
            base: typing.Optional[urllib.parse.ParseResult] = None
    ) -> typing.Optional[str]:
        """
        Transform the partly defined target string to a full URL

        The implementation of this method is partly based
        on RFC 3986, section 5.1 and 5.2 (with modifications).

        :param target: anything that seems to be an URI, relative or absolute
        :param base: optional base URI used to correctly find absolute paths
            for relative resource indicators (uses the remote URL if absent)
        :return: a full URL that can be used to request further resources,
            if possible and the target matched the criteria (otherwise None)
        """

        def merge_paths(a: urllib.parse.ParseResult, b: str) -> str:
            """
            Merge two paths, where `a` should be a base and `b` should be a reference
            """

            if not b.startswith("/"):
                b = "/" + b
            if a.netloc != "" and a.path == "":
                return b
            return "/".join(a.path.split("/")[:-1]) + b

        def remove_dot_segments(p: str) -> str:
            """
            Remove the dot segments of a path `p`
            """

            if "./" in p or "/." in p:
                self.logger.warning("Feature not implemented: remove_dot_segments")
            return p

        url = urllib.parse.urlparse(target)
        scheme, netloc, path, params, query, fragment = url

        # TODO: section 5.1, order of precedence
        if base is None:
            base = self.job.remote_url

        # Unknown schemes are ignored (e.g. mailto:) and a given schema indicates
        # an absolute URL which should not be processed (only filtered)
        if scheme != "" and scheme.lower() not in ("http", "https"):
            return
        elif scheme == "":
            if self.job.https_mode == 0:
                scheme = self.job.remote_url.scheme
            elif self.job.https_mode == 1 or self.job.https_mode == 3:
                scheme = "https"
            elif self.job.https_mode == 2:
                scheme = "http"
        elif netloc != "" and netloc.lower() == self.job.netloc.lower():
            return urllib.parse.urlunparse(
                (scheme, netloc, remove_dot_segments(path), params, query, "")
            )

        # Other network locations are ignored (so we don't traverse the whole web)
        if netloc != "" and netloc.lower() != self.job.netloc.lower():
            return
        elif netloc != "":
            return urllib.parse.urlunparse(
                (scheme, netloc, remove_dot_segments(path), params, query, "")
            )

        netloc = self.job.netloc

        # Determine the new path
        if path == "":
            path = base.path
            if query == "":
                query = base.query
        else:
            if path.startswith("/"):
                path = remove_dot_segments(path)
            else:
                path = remove_dot_segments(merge_paths(base, path))
        return urllib.parse.urlunparse(
            (scheme, netloc, remove_dot_segments(path), params, query, "")
        )

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
    :param handler_options: dictionary of various options that will
        be given to a job's handler class to tweak its behavior
    """

    handler_options: dict
    """Various options directly passed to the job's handler class"""
    descendants: typing.List[DownloadJob]
    """List of follow-up jobs in case of errors, if available"""

    def __init__(self, job: DownloadJob, handler_options: dict):
        self.job = job
        self.logger = job.logger
        self.handler_options = handler_options
        self.descendants = []
