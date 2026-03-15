"""Compatibility helpers for importing cadquery in PyInstaller bundles.

cadquery unconditionally imports ``casadi`` for its assembly constraint solver,
but this project uses only basic geometry operations (Workplane, box, extrude)
and never invokes the solver.  On Windows PyInstaller bundles the casadi native
DLL (``_casadi.pyd``) is typically missing, causing an ``ImportError`` at import
time.

This module provides:

* :func:`stub_casadi` — inject a lightweight stub ``casadi`` package into
  ``sys.modules`` so that ``import cadquery`` succeeds without a real casadi.
* :func:`ensure_cq` — lazy-import cadquery on first call (calling
  :func:`stub_casadi` first) and cache the module in a global.

All eleven model modules import from here instead of duplicating the stub logic.
"""
from __future__ import annotations

import sys
import types
from typing import Any

# Cached cadquery module — populated by ensure_cq() on first call.
_cq: Any = None


class _CasadiStub(types.ModuleType):
    """Module stub that returns itself for any non-dunder attribute access.

    Dunder attributes (``__repr__``, ``__file__``, etc.) are delegated to the
    normal ``ModuleType`` machinery so that ``repr(stub)`` and ``str(stub)``
    work without triggering infinite recursion.
    """

    def __getattr__(self, name: str) -> _CasadiStub:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return self


def stub_casadi() -> None:
    """Inject a fake ``casadi`` package into ``sys.modules`` if absent.

    The stub uses a permissive :meth:`__getattr__` so that any attribute
    access (``ca.Opti``, ``ca.MX``, etc.) returns a harmless dummy instead
    of raising :exc:`AttributeError`.
    """
    if "casadi" not in sys.modules:
        _fake = _CasadiStub("casadi")
        _fake.__path__ = []  # type: ignore[attr-defined]
        sys.modules["casadi"] = _fake
        sys.modules["casadi.casadi"] = _fake


def ensure_cq() -> Any:
    """Import cadquery on first use and return the cached module.

    Calls :func:`stub_casadi` before the import so that the casadi
    dependency is satisfied even when the native library is absent.
    """
    global _cq  # noqa: PLW0603
    if _cq is None:
        stub_casadi()
        import cadquery as _cadquery

        _cq = _cadquery
    return _cq
