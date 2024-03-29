"""
Various job content handler classes, grouped by the content's MIME type
"""

import typing
import urllib.parse

import bs4

from . import helper as _helper


class BaseContentHandler:
    """
    Base class for all variants of content handler classes

    A subclass should implement the ``analyze`` class method which
    is dedicated to actually handle the server's response.
    This method should only accept one argument, the download
    job itself. That ``DownloadJob`` object should have an attribute
    ``options`` which can be accessed like a mapping or a namespace.
    An implementation should document which attributes are required
    by it, but it should not assume that certain keys are present.
    The default classes have properly set defaults, though. Therefore,
    a subclass must provide reasonable default values for missing keys.
    The return value of that method should provide the complete and
    final content as it should be stored in the target file on disk.
    Note that the handler should not set the ``final_content`` attribute.

    Additionally, subclasses must set the class variable MIME_TYPE
    to indicate which mime types are support using ``accepts`` method.
    """

    MIME_TYPE: typing.ClassVar[typing.List[str]]
    """List of MIME types that can be analyzed by the specific handler class"""

    @classmethod
    def accepts(cls, content_type: str) -> bool:
        """
        Determine whether the given content MIME type is accepted by the handler
        """

        return content_type.lower().split(";")[0].strip() in map(
            lambda s: s.lower(), cls.MIME_TYPE
        )

    @classmethod
    def analyze(cls, job) -> typing.AnyStr:
        raise NotImplementedError

    @classmethod
    def _check_type(cls, job):
        """
        Raise a TypeError if job is no ``DownloadJob`` instance
        """

        # TODO: improve or remove type checking
        if not any(map(lambda c: c.__name__ == "DownloadJob", type(job).mro())):
            raise TypeError(f"Expected DownloadJob, got {type(job)}")


class _DummyContentHandler(BaseContentHandler):
    """
    Dummy content handler returning the exact content without modification

    A subclass must set the ``MIME_TYPES`` class attribute accordingly!
    """

    @classmethod
    def analyze(cls, job) -> typing.AnyStr:
        cls._check_type(job)
        job.logger.debug(f"{cls.__name__} doesn't implement analyze yet...")
        return job.response.text


class PlaintextContentHandler(_DummyContentHandler):
    MIME_TYPE = ["text/plain"]


class HTMLContentHandler(BaseContentHandler):
    """
    Handler class for HTML content
    """

    MIME_TYPE = ["text/html"]

    @classmethod
    def analyze(cls, job) -> typing.AnyStr:
        """
        Analyze and edit the job's content, extracting potential new targets

        Supported keys in the ``options`` storage:
         *  ``ascii_only``
         *  ``load_hyperlinks``
         *  ``load_images``
         *  ``load_javascript``
         *  ``load_stylesheets``
         *  ``lowered_paths``
         *  ``pretty_html``
         *  ``rewrite_references``

        :param job: the download job that should be handled and analyzed
        :return: the content of the file that should be written to disk
        """

        # TODO: add/ensure support for non-default charsets (HTTP header field)

        def get_relative_path(ref: str) -> str:
            """
            Get the relative path pointing from the current file towards ``ref``

            :param ref: any kind of reference, but works best for absolute URLs
                (therefore, one should better make it an absolute URL before)
            :return: relative path pointing from the current file towards the reference
            """

            path = urllib.parse.urlparse(ref).path
            if job.options.ascii_only:
                path = _helper.convert_to_ascii_only(
                    path,
                    job.options.ascii_conversion_table
                )
            if job.options.lowered_paths:
                path = path.lower()
            if path.startswith("/"):
                path = path[1:]
            return path

        def handle_tag(
                tag_type: str,
                attr_name: str,
                filter_func: typing.Callable[[bs4.element.Tag], bool]
        ):
            """
            Handle all tags of a specific type using one of its attributes

            This method extracts the URLs found in all tags of the specified type,
            provided the name of the attribute where the URL will be found is
            present as well. If rewriting of references had been enabled, this step
            will also be done in this method. Use the filter function to restrict
            the range of scanned and processed tags in the input file.

            :param tag_type: type of HTML tag (e.g. ``a`` or ``img``)
            :param attr_name: attribute name for that tag (e.g. ``href`` or ``src``)
            :param filter_func: function which accepts exactly one parameter, one
                single HTML tag, and determines whether this tag should be analyzed
                (filtering and processing of URLs takes place after this filter, so
                one doesn't need to care about e.g. schemes or other network locations)
            """

            nonlocal job
            nonlocal soup

            for tag in soup.find_all(tag_type):
                if tag.has_attr(attr_name) and filter_func(tag):
                    target = _helper.find_absolute_reference(
                        tag.get(attr_name),
                        job.netloc,
                        job.remote_url,
                        job.options.https_mode,
                        base
                    )

                    if target is not None:
                        job.references.add(target)
                        relative_path = get_relative_path(target)
                        tag.attrs[attr_name] = relative_path

        def stylesheet_filter_func(tag: bs4.element.Tag) -> bool:
            """
            Filter function for stylesheet tags only
            """

            if tag.has_attr("rel"):
                is_css = "stylesheet" in tag.get("rel")
                enabled = not tag.has_attr("disabled")
                if is_css and enabled:
                    return True
            return False

        cls._check_type(job)

        # Extract the document's base URI
        base = None
        soup = bs4.BeautifulSoup(job.response.text, features="html.parser")
        if soup.base is not None and soup.base.has_attr("href"):
            base = soup.base.get("href")
            if urllib.parse.urlparse(base).netloc == "":
                base = urllib.parse.urljoin(job.netloc, base)
            base = urllib.parse.urlparse(base)
        job.logger.debug(f"Base: {job}")

        # Remove all `base` tags
        while soup.base:
            job.logger.debug("Removing (one of) the `base` tag(s)")
            soup.base.replace_with("")

        # Handle the various types of references, if enabled
        if job.options.include_hyperlinks:
            handle_tag("a", "href", lambda x: True)
        if job.options.include_stylesheets:
            # TODO: add support for icons and scripts added by `link` tags
            handle_tag("link", "href", stylesheet_filter_func)
        if job.options.include_javascript:
            handle_tag("script", "src", lambda x: True)
        if job.options.include_images:
            handle_tag("img", "src", lambda x: True)

        # Determine the final content, based on the specified options
        if job.options.pretty_html:
            return soup.prettify()
        if job.options.rewrite_references:
            return soup.decode()
        return job.response.text


class CSSContentHandler(_DummyContentHandler):
    MIME_TYPE = ["text/css"]


class JavaScriptContentHandler(_DummyContentHandler):
    MIME_TYPE = ["application/javascript"]


ALL_DEFAULT_HANDLER_CLASSES: typing.List[typing.Type[BaseContentHandler]] = [
    PlaintextContentHandler,
    HTMLContentHandler,
    CSSContentHandler,
    JavaScriptContentHandler
]
