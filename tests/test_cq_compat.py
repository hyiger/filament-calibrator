"""Tests for filament_calibrator._cq_compat — casadi stub and lazy cadquery import."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import filament_calibrator._cq_compat as mod

from filament_calibrator._cq_compat import (
    _CasadiStub,
    ensure_cq,
    stub_casadi,
)


# ---------------------------------------------------------------------------
# _CasadiStub
# ---------------------------------------------------------------------------


class TestCasadiStub:
    def test_returns_self_for_regular_attributes(self):
        stub = _CasadiStub("casadi")
        assert stub.Opti is stub
        assert stub.MX is stub
        assert stub.DM is stub

    def test_chained_access_returns_self(self):
        stub = _CasadiStub("casadi")
        assert stub.Opti.solver.something is stub

    def test_raises_attribute_error_for_dunder(self):
        stub = _CasadiStub("casadi")
        # Dunder names not provided by ModuleType should raise AttributeError
        import pytest

        with pytest.raises(AttributeError):
            stub.__nonexistent_dunder__  # noqa: B018

    def test_repr_does_not_recurse(self):
        """repr() must not cause infinite recursion (was a bug before)."""
        stub = _CasadiStub("casadi")
        stub.__path__ = []  # type: ignore[attr-defined]
        # Should not raise RecursionError
        result = repr(stub)
        assert isinstance(result, str)

    def test_str_does_not_recurse(self):
        stub = _CasadiStub("casadi")
        stub.__path__ = []  # type: ignore[attr-defined]
        result = str(stub)
        assert isinstance(result, str)

    def test_is_module_subclass(self):
        stub = _CasadiStub("casadi")
        assert isinstance(stub, types.ModuleType)


# ---------------------------------------------------------------------------
# stub_casadi
# ---------------------------------------------------------------------------


class TestStubCasadi:
    def test_creates_stub_when_not_loaded(self):
        saved = sys.modules.pop("casadi", None)
        saved_sub = sys.modules.pop("casadi.casadi", None)
        try:
            stub_casadi()
            fake = sys.modules["casadi"]
            assert isinstance(fake, _CasadiStub)
            assert isinstance(sys.modules["casadi.casadi"], _CasadiStub)
            # Both entries point to the same stub instance
            assert sys.modules["casadi.casadi"] is fake
            # __getattr__ returns the stub itself for regular attributes
            assert fake.Opti is fake
            # __path__ is set so it looks like a package
            assert fake.__path__ == []  # type: ignore[attr-defined]
        finally:
            sys.modules.pop("casadi", None)
            sys.modules.pop("casadi.casadi", None)
            if saved is not None:
                sys.modules["casadi"] = saved
            if saved_sub is not None:
                sys.modules["casadi.casadi"] = saved_sub

    def test_skips_when_already_loaded(self):
        sentinel = MagicMock()
        with patch.dict(sys.modules, {"casadi": sentinel}):
            stub_casadi()
            assert sys.modules["casadi"] is sentinel


# ---------------------------------------------------------------------------
# ensure_cq
# ---------------------------------------------------------------------------


class TestEnsureCq:
    def test_imports_cadquery_when_none(self):
        saved = mod._cq
        try:
            mod._cq = None
            mock_cq = MagicMock()
            with patch.dict("sys.modules", {"cadquery": mock_cq}):
                result = ensure_cq()
            assert result is mock_cq
            assert mod._cq is mock_cq
        finally:
            mod._cq = saved

    def test_returns_cached_on_subsequent_calls(self):
        saved = mod._cq
        try:
            sentinel = MagicMock()
            mod._cq = sentinel
            result = ensure_cq()
            assert result is sentinel
        finally:
            mod._cq = saved
