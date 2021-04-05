"""
Various constant values used in the project
"""

import enum as _enum
import typing as _typing


VERSION = (0, 1, 0)  # scheme: major, minor, release
VERSION_STRING = f"v{'.'.join(map(str, VERSION))}"


class RunnerState(_enum.Enum):
    CREATED = _enum.auto()  # the runner has just been created
    WORKING = _enum.auto()  # the runner processes jobs
    WAITING = _enum.auto()  # the runner waits for new jobs to be available
    ENDING = _enum.auto()   # the runner processes its last job
    EXITED = _enum.auto()   # the runner exited gracefully
    CRASHED = _enum.auto()  # the runner crashed due to unhandled exception


class HTTPSMode(_enum.Enum):
    DEFAULT = _enum.auto()      # do not care about HTTP or HTTPS
    HTTP_ONLY = _enum.auto()    # try enforcing HTTP
    HTTPS_ONLY = _enum.auto()   # try enforcing HTTPS
    HTTPS_FIRST = _enum.auto()  # try HTTPS first, then fall back to HTTP on errors


DEFAULT_ACCEPTED_RESPONSE_CODES: _typing.Tuple[int] = (200,)

DEFAULT_ALLOW_OVERWRITING_FILES: bool = True

DEFAULT_ASCII_ONLY_REFERENCES: bool = False
DEFAULT_ASCII_REPLACEMENT_CHAR: str = "_"

DEFAULT_COMPRESSED_HTML: bool = False

DEFAULT_DOWNLOADER_THREAD_COUNT: int = 4

DEFAULT_HTTPS_MODE: HTTPSMode = HTTPSMode.DEFAULT

DEFAULT_INCLUDE_FONTS: bool = False
DEFAULT_INCLUDE_HYPERLINKS: bool = True
DEFAULT_INCLUDE_IMAGES: bool = False
DEFAULT_INCLUDE_JAVASCRIPT: bool = True
DEFAULT_INCLUDE_STYLESHEETS: bool = True
DEFAULT_INCLUDE_THIRD_PARTY_RESOURCES: bool = False

DEFAULT_JOB_MANAGER_FULL_MODE: bool = False

DEFAULT_LOGFILE: _typing.Optional[str] = None

DEFAULT_LOWERED_PATHS: bool = False

DEFAULT_MENTION_OVERWRITING_FILES: bool = True

DEFAULT_PRETTY_CSS: bool = False
DEFAULT_PRETTY_HTML: bool = False
DEFAULT_PRETTY_JAVASCRIPT: bool = False

DEFAULT_QUEUE_ACCESS_TIMEOUT: float = 0.1

DEFAULT_RESPECT_REDIRECTS: bool = True

DEFAULT_REWRITE_REFERENCES: bool = True

DEFAULT_RUNNER_CRASH_ON_ERROR: bool = False

DEFAULT_STATUS_UPDATES: _typing.Optional[float] = None

DEFAULT_USER_AGENT: str = "Mozilla/5.0 (compatible; WebsiteCrawler)"

DEFAULT_UNIQUE_FILENAMES: bool = False

DEFAULT_VERBOSE: bool = False
