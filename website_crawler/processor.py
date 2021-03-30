"""
Module containing processors which retrieve resources
from the remote server and trigger the analyze using
the correct handler classes, gathering new references
"""

import os
import typing
import logging
import mimetypes
import urllib.parse

import requests

from . import constants as _constants, helper as _helper, job as _job


class BaseProcessor:
    """
    Base class for job processors

    This class provides convenient methods making the
    implementation of correct processors easier.
    """

    job: _job.DownloadJob
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

        See the `helper` module for the actual implementation of this method.
        """

        return _helper.find_absolute_reference(
            target,
            self.job.netloc,
            self.job.remote_url,
            self.job.https_mode,
            base
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

    Supported keys in the `options` dictionary:
     *  ``ascii_only``
     *  ``lowered``
     *  ``respect_redirects``

    :param job: description of a single download job (will also be
        accessed in read-write manner to store various flags and data)
    :param options: dictionary of various options that will be given
        to a job's handler class to tweak its behavior but might also
        be used by the processor in the one way or the other (note that
        none of those classes should rely on any value to be present)
    """

    options: dict
    """Various options used to alter the job's processing and analyze"""
    descendants: typing.List[_job.DownloadJob]
    """List of follow-up jobs in case of errors, if available"""

    def __init__(self, job: _job.DownloadJob, options: dict):
        self.job = job
        self.logger = job.logger
        self.options = options
        self.descendants = []

    def run(self) -> bool:
        """
        Perform the actual work as a blocking process

        :return: True if all operations completed successfully, False otherwise
            (the job's attribute `exception` might hold more details about the
            error; the processor's attribute `descendants` might hold follow-up
            jobs that could be used instead to fix this error, if possible)
        """

        if self.job.started:
            self.logger.warning(f"{self.job} has already been started. Parallel access?")
        self.job.started = True

        self.logger.debug(f"Currently processing: {self.job.remote_path}")
        try:
            self.job.response = requests.get(
                self.job.remote_path,
                headers={"User-Agent": self.job.user_agent}
            )

        # Catch SSL errors and eventually try to fetch the resource via HTTP again
        except requests.exceptions.SSLError as exc:
            self.job.exception = exc
            msg = f"SSL Error: {exc} (while fetching {self.job})"
            if self.job.https_mode == 3 and self.job.remote_url.scheme == "https":
                self.descendants.append(
                    self.job.copy(self.job.remote_url._replace(scheme="http"))
                )
                self.logger.warning(msg)
            else:
                self.logger.error(msg)
            self.job.delayed = True
            return False

        self.job.response_code = self.job.response.status_code

        # Abort further operation on failed response
        if self.job.response_code != 200:
            self.logger.error(
                f"Received code {self.job.response_code} "
                f"for {self.job.remote_path}. Skipping."
            )
            self.job.delayed = True
            return False

        # Adopt the new remote URL if there were some redirects
        if len(self.job.response.history) > 0 and self.options.get(
                "respect_redirects",
                _constants.DEFAULT_PROCESSOR_RESPECT_REDIRECTS
        ):
            new_url = self.job.response.url
            new_url_parsed = urllib.parse.urlparse(new_url)
            if new_url_parsed.netloc != self.job.netloc:
                self.logger.warning(f"Redirecting to another network location: {new_url}")
                self.logger.debug("The redirected target location will become a new job.")
                self.descendants.append(self.job.copy(new_url_parsed))
                self.job.delayed = True
                return False

            self.logger.debug(f"Respecting redirect to {new_url}...")
            self.job.remote_path = new_url
            self.job.remote_url = new_url_parsed

        # Determine the content type of the response
        for header in self.job.response.headers:
            if header.lower() == "content-type":
                self.job.response_type = self.job.response.headers[header]
        if self.job.response_type is None:
            self.job.response_type, _ = mimetypes.guess_type(self.job.remote_path)

        # Determine the correct handler class and analyze the content
        handler_class = None
        for handler_class in self.job.handler:
            if handler_class.accepts(self.job.response_type):
                self.logger.debug(f"Using {handler_class} to analyze {self.job}")
                content = handler_class.analyze(self.job, self.options)
                break
        else:
            self.logger.warning(f"No handler class found for {self.job}")
            content = self.job.response.content

        # Report problems that might have occurred after analyzing
        if content is None:
            self.logger.error("No file content available.")
        elif not isinstance(content, (str, bytes)):
            self.logger.error(f"Handler class returned type {type(content)}!")
        if content is None or not isinstance(content, (str, bytes)):
            self.logger.info(
                "A handler class should either return str or bytes. "
                "The error above indicates problems with the class "
                f"{handler_class}. Please fix its analyze() class method."
            )
            content = b""
        self.job.final_content = content

        # Determine the filename under which the content should be stored
        path = self.job.remote_url.path
        if self.options.get("ascii_only", False):
            path = _helper.convert_to_ascii_only(path, _helper.SMALL_ASCII_CONVERSION_TABLE)
        if self.options.get("lowered", False):
            path = path.lower()
        if path.startswith("/"):
            path = path[1:]
        if len(path) == "":
            self.logger.warning("Empty path detected. Added 'index.html'!")
            path = "index.html"

        # Determine the full local filename (path) from the local base
        local_path = os.path.join(self.job.local_base, path)
        if local_path.endswith("/"):
            self.logger.warning(
                f"Added suffix 'index.html' because "
                f"'{local_path}' ended with '/'!"
            )
            local_path = os.path.join(local_path, "index.html")
        self.job.local_path = local_path

        if not self.save():
            self.logger.warning("Saving the final content failed.")

        self.job.finished = True
        return True
