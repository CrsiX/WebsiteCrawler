"""
Module proving a standard way to carry various options
"""

import typing

try:
    from . import constants as _constants
except ImportError:
    import constants as _constants


class Namespace(dict):
    """
    Subclassed dict that allows accessing its items like attributes
    """

    def __getattr__(self, key: str):
        return self.__getitem__(key)

    def __setattr__(self, key: str, value: typing.Any):
        self.__setitem__(key, value)

    def __setitem__(self, key: str, value: typing.Any):
        if not isinstance(key, str):
            raise TypeError(f"Keys must be str, not {type(key)}")
        if not key.isidentifier():
            raise KeyError(f"Keys must be valid identifiers, not '{key}'")
        super().__setitem__(key, value)


class Options(Namespace):
    """
    Collection of options with respect to default values

    It's recommended to use this class whenever a function,
    method or class requires an argument ``options``. One could
    easily give a normal dictionary with the required attributes
    already set. But this class tries to avoid KeyErrors by
    looking up the default value for missing keys automatically.

    Note that a call to ``copy`` will return an ``Options`` object.
    The methods ``popitem`` and ``setdefault`` don't perform anything
    for objects of this class on purpose. The methods ``items``,
    ``keys`` and ``values`` work exactly like for dictionaries, i.e.
    they return (set-like) views. The method ``update`` ensures that
    all keys are strings and raises TypeErrors if they aren't.
    """

    def __repr__(self):
        if len(self) == 0:
            return "Options()"
        try:
            width = max(len(name) for name in self)
        except TypeError as exc:
            raise TypeError("Do not use non-string keys!") from exc
        return "Options(\n" + "\n".join(
            f"  {key:<{width}} = {self[key]}" for key in sorted(self.keys())
        ) + "\n)"

    def __getitem__(self, item: str):
        if item in self:
            return super().__getitem__(item)
        elif isinstance(item, str) and hasattr(_constants, f"DEFAULT_{item.upper()}"):
            return getattr(_constants, f"DEFAULT_{item.upper()}")
        else:
            raise KeyError(item)

    def copy(self) -> "Options":
        return Options(super().copy())

    def popitem(self, *args, **kwargs):
        """
        Don't do anything, on purpose
        """

        pass

    def setdefault(self, *args, **kwargs):
        """
        Don't do anything, on purpose
        """

        pass

    def update(self, mapping: typing.Mapping = None, **kwargs: dict):
        if mapping is not None:
            if isinstance(mapping, typing.Mapping):
                for k in mapping:
                    self[k] = mapping[k]
            elif isinstance(mapping, typing.Iterable):
                for k, v in mapping:
                    self[k] = v
        for k in kwargs:
            self[k] = kwargs[k]
