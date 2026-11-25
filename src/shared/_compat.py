"""
MicroPython compatibility shims for stdlib `dataclasses` and `enum`.

On the host PC (CPython 3.12+), imports the real stdlib `dataclass`, `IntEnum`,
and `StrEnum`. On Pybricks MicroPython (which omits `dataclasses` and `enum`),
provides lightweight fallbacks so shared models and enums work identically.
"""

TYPE_CHECKING = False
if TYPE_CHECKING:
    from dataclasses import dataclass
    from enum import IntEnum, StrEnum
else:
    try:
        from enum import IntEnum, StrEnum
    except ImportError:
        IntEnum = object
        StrEnum = object

    try:
        from dataclasses import dataclass
    except ImportError:
        # Note: MicroPython strips uninitialized field annotations (`x: int`), so every
        # field on a shared dataclass must define a default value to be captured here.
        def dataclass(cls=None, **_kwargs):
            def wrap(c):
                defaults = {}
                for k, v in c.__dict__.items():
                    if (
                        not k.startswith("__")
                        and not callable(v)
                        and not isinstance(v, (staticmethod, classmethod, property))
                    ):
                        defaults[k] = v

                def __init__(self, **kwargs):
                    for k, default in defaults.items():
                        setattr(self, k, kwargs[k] if k in kwargs else default)

                def __repr__(self):
                    fields = ", ".join(f"{k}={repr(getattr(self, k))}" for k in defaults)
                    return f"{c.__name__}({fields})"

                def __eq__(self, other):
                    if not isinstance(other, c):
                        return False
                    return all(getattr(self, k) == getattr(other, k) for k in defaults)

                c.__init__ = __init__
                c.__repr__ = __repr__
                c.__eq__ = __eq__
                return c

            return wrap if cls is None else wrap(cls)
