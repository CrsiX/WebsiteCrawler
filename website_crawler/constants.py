"""
Various constant values used in the project
"""

from enum import Enum as _Enum, auto as _auto
from typing import Tuple as _Tuple


class RunnerState(_Enum):
    CREATED = _auto()  # the runner has just been created
    WORKING = _auto()  # the runner processes jobs
    WAITING = _auto()  # the runner waits for new jobs to be available
    ENDING = _auto()   # the runner processes its last job
    EXITED = _auto()   # the runner exited gracefully
    CRASHED = _auto()  # the runner crashed due to unhandled exception


DEFAULT_ACCEPTED_RESPONSE_CODES: _Tuple[int] = (200,)

DEFAULT_ALLOW_OVERWRITING_FILES: bool = True

DEFAULT_ASCII_ONLY_REFERENCES: bool = False
DEFAULT_ASCII_REPLACEMENT_CHAR: str = "_"

DEFAULT_DOWNLOADER_THREAD_COUNT: int = 4

DEFAULT_HTTPS_MODE: int = 3

DEFAULT_INCLUDE_FONTS: bool = False
DEFAULT_INCLUDE_HYPERLINKS: bool = True
DEFAULT_INCLUDE_IMAGES: bool = False
DEFAULT_INCLUDE_JAVASCRIPT: bool = True
DEFAULT_INCLUDE_STYLESHEETS: bool = True
DEFAULT_INCLUDE_THIRD_PARTY_RESOURCES: bool = False

DEFAULT_JOB_MANAGER_FULL_MODE: bool = False

DEFAULT_LOWERED_PATHS: bool = False

DEFAULT_MENTION_OVERWRITING_FILES: bool = True

DEFAULT_PRETTY_HTML: bool = False

DEFAULT_PROCESSOR_RESPECT_REDIRECTS: bool = True

DEFAULT_QUEUE_ACCESS_TIMEOUT: float = 0.1

DEFAULT_REWRITE_REFERENCES: bool = True

DEFAULT_RUNNER_CRASH_ON_ERROR: bool = False

DEFAULT_USER_AGENT_STRING: str = "Mozilla/5.0 (compatible; WebsiteCrawler)"

DEFAULT_UNIQUE_FILENAMES: bool = False
