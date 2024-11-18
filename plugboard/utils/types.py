"""Provides reusable type annotations."""

import typing as _t


AsyncCallable = _t.Callable[..., _t.Coroutine[_t.Any, _t.Any, _t.Any]]
