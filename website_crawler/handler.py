"""
Various job content handler classes, grouped by the content's MIME type
"""

import typing


class BaseContentHandler:
    """
    Base class for all variants of content handler classes

    A subclass should implement the `__call__` method which
    is dedicated to actually handle the server's response.
    This method should accept only one argument, the download
    job itself. The signature should allow any number of
    arguments though, to enable other handlers to use them.
    The return value of that method signals the caller whether
    the content of the given job has been edited as a side-effect.
    """

    mime_type: typing.List[str]
    """Specifier the mime-type that can be analyzed by the specific handler class"""

    def accept(self, content_type: str) -> bool:
        """
        Determine whether the given content MIME type is accepted by the handler
        """

        return content_type.lower() in map(lambda s: s.lower(), self.mime_type)

    def __call__(self, *args, **kwargs) -> bool:
        raise NotImplementedError
