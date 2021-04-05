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
    already set. But this class avoids KeyErrors by looking up
    the default value for missing keys automatically.
    """

    def __repr__(self):
        if len(self) == 0:
            return "Options()"
        width = max(len(name) for name in self)
        return "Options(\n" + "\n".join(
            f"  {key:<{width}} = {self[key]}" for key in sorted(self.keys())
        ) + "\n)"

    def __getitem__(self, item: str):
        if item in self:
            return super().__getitem__(item)
        elif hasattr(_constants, f"DEFAULT_{item.upper()}"):
            return getattr(_constants, f"DEFAULT_{item.upper()}")
        else:
            raise KeyError(item)
