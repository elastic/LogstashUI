#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Decorators and their helper functions"""

from collections.abc import Callable
from functools import wraps
import inspect
from pathlib import Path
from typing import Any, Literal, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def to_path(arg: Any) -> Any:
    """Convert a string (or path-like) to a pathlib.Path; leave others unchanged.

    This helper is segmented for easy unit testing and reuse.

    Args:
        arg: The value to potentially convert.

    Returns:
        A pathlib.Path if conversion succeeded, otherwise the original ``arg``
        (including ``None``, numbers, etc.).

    Examples:
        >>> isinstance(to_path("/tmp/file.txt"), Path)
        True
        >>> p = Path("/tmp")
        >>> to_path(p) is p  # preserves identity for existing Paths
        True
        >>> to_path(None) is None
        True
        >>> to_path(42)
        42
        >>> to_path(b"/bytes/path")  # bytes also convert (Unix-style)
        PosixPath('/bytes/path')
    """
    if isinstance(arg, Path):
        return arg
    try:
        return Path(arg)
    except TypeError:
        # Non-path-like values (None, int, list, custom objects, etc.) stay untouched
        return arg


def pathify(*param_names: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that converts named arguments from str (or path-like) to pathlib.Path.

    This lets callers pass either strings or Path objects for the listed parameters
    while guaranteeing the decorated function always receives pathlib.Path objects
    (or the original non-convertible value).

    Handles positional args, keyword args, keyword-only args, defaults, *args/**kwargs,
    and mixed calls. Uses ``inspect.signature`` for full robustness.

    Args:
        *param_names: Names of the function parameters to convert
            (e.g. ``"src"``, ``"dst"``).

    Returns:
        The wrapped function.

    Examples:
        >>> @pathify("src", "dst")
        ... def copy_file(src, dst="/output/default"):
        ...     # Inside: both are always Path (or original non-str)
        ...     return src, dst
        >>> result = copy_file("/in.txt", Path("/out"))
        >>> isinstance(result[0], Path) and isinstance(result[1], Path)
        True
        >>> # Defaults that are strings are converted too
        >>> copy_file("/in.txt")[1] == Path("/output/default")
        True
        >>> # Non-convertible values are left alone
        >>> @pathify("p")
        ... def func(p=None):
        ...     return p
        >>> func() is None
        True
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        # Signature captured once (performance)
        func_sig = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> R:
            """Wrapped function with automatic path conversion."""
            bound = func_sig.bind(*args, **kwargs)
            bound.apply_defaults()  # crucial so defaults (even strings) are converted

            for name in param_names:
                if name in bound.arguments:
                    bound.arguments[name] = to_path(bound.arguments[name])

            return func(*bound.args, **bound.kwargs)

        return wrapper

    return decorator


def path_exists(
    *param_names: str,
    kind: Literal["exists", "is_file", "is_dir"] = "exists",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator that verifies named Path arguments exist (and match the requested kind).

    Place it *below* ``@pathify`` so it receives already-converted Paths.

    Raises ``FileNotFoundError`` with a clear message if any required path fails
    the check.

    Re-converts + re-binds the Path for maximum robustness (works even if stacking
    order is reversed).

    Args:
        *param_names: Parameter names to validate (e.g. "binary_path", "config").
        kind: What to check - "exists" (default), "is_file", or "is_dir".

    Returns:
        Decorated function.

    Examples:
        >>> @pathify("p")
        ... @path_exists("p", kind="is_file")
        ... def read_file(p):
        ...     return p.read_text()
        >>> # (doctest skipped - requires real file)
    """
    if kind not in {"exists", "is_file", "is_dir"}:
        raise ValueError(
            f"kind must be one of 'exists', 'is_file', 'is_dir', got {kind!r}"
        )

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        sig = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> R:
            """Inner wrapper - validates after pathify conversion."""
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            for name in param_names:
                if name in bound.arguments:
                    val = bound.arguments[name]
                    p = to_path(val)

                    if not isinstance(p, Path):
                        raise TypeError(
                            f"Argument '{name}' must be path-like, got "
                            f"{type(val).__name__}"
                        )

                    if not getattr(p, kind)():
                        if kind == "exists":
                            msg = f"Arg {p} ('{name}') does not exist"
                        elif kind == "is_file":
                            msg = f"Arg {p} ('{name}') is not a file"
                        else:  # is_dir
                            msg = f"Arg {p} ('{name}') is not a directory"
                        raise FileNotFoundError(msg)

                    # Ensure downstream functions receive a Path
                    bound.arguments[name] = p

            return func(*bound.args, **bound.kwargs)

        return wrapper

    return decorator
