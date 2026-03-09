"""Parametric two-tower model for retraction calibration.

Generates two cylindrical towers on a shared rectangular base plate.
The towers are spaced apart so that the slicer generates travel moves
between them, triggering retraction.  When printed with firmware
retraction enabled and ``M207`` commands inserted at each height level,
the user can inspect stringing between towers to find the optimal
retraction distance.

All dimensions are in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_retraction_tower_stl() to avoid
# loading the heavy OCCT/casadi native libraries at module-import time.
cq: Any = None  # populated by _ensure_cq()


def _stub_casadi() -> None:
    """Provide a stub ``casadi`` package when the real one is not yet loaded.

    cadquery unconditionally imports casadi for its assembly constraint
    solver, but this project uses only basic geometry operations and never
    invokes the solver.  On Windows PyInstaller bundles the casadi native
    DLL (``_casadi.pyd``) is typically missing.  Injecting a lightweight
    stub lets cadquery import cleanly.

    The stub uses a permissive ``__getattr__`` so that any attribute access
    (``ca.Opti``, ``ca.MX``, etc.) returns a harmless dummy instead of
    raising ``AttributeError``.
    """
    import sys

    if "casadi" not in sys.modules:
        import types

        class _CasadiStub(types.ModuleType):
            """Module stub that returns itself for any attribute access."""

            def __getattr__(self, name: str) -> _CasadiStub:
                return self

        _fake = _CasadiStub("casadi")
        _fake.__path__ = []  # type: ignore[attr-defined]
        sys.modules["casadi"] = _fake
        sys.modules["casadi.casadi"] = _fake


def _ensure_cq() -> None:
    """Import cadquery on first use and cache in module globals."""
    global cq  # noqa: PLW0603
    if cq is None:
        _stub_casadi()
        import cadquery as _cq  # type: ignore[import-untyped]

        cq = _cq

# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

TOWER_DIAMETER: float = 10.0
"""Diameter of each cylindrical tower in mm."""

TOWER_SPACING: float = 50.0
"""Centre-to-centre distance between the two towers in mm."""

BASE_LENGTH: float = 70.0
"""X dimension of the rectangular base plate in mm."""

BASE_WIDTH: float = 20.0
"""Y dimension of the rectangular base plate in mm."""

BASE_HEIGHT: float = 1.0
"""Height of the base plate in mm (for bed adhesion)."""

LEVEL_HEIGHT: float = 1.0
"""Default height per retraction level in mm."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class RetractionTowerConfig:
    """Parameters for the retraction calibration two-tower model.

    Attributes
    ----------
    num_levels:     Number of retraction-length levels.
    level_height:   Height per level in mm.
    tower_diameter: Diameter of each cylindrical tower in mm.
    tower_spacing:  Centre-to-centre distance between towers in mm.
    base_length:    X dimension of the base plate in mm.
    base_width:     Y dimension of the base plate in mm.
    base_height:    Height of the base plate in mm.
    filament_type:  Label for filament type (e.g. ``"PLA"``).
    """
    num_levels: int
    level_height: float = LEVEL_HEIGHT
    tower_diameter: float = TOWER_DIAMETER
    tower_spacing: float = TOWER_SPACING
    base_length: float = BASE_LENGTH
    base_width: float = BASE_WIDTH
    base_height: float = BASE_HEIGHT
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def total_height(config: RetractionTowerConfig) -> float:
    """Return the total Z height of the model (base + tower levels)."""
    return config.base_height + config.num_levels * config.level_height


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_base(config: RetractionTowerConfig) -> cq.Workplane:
    """Create the rectangular base plate centred at the XY origin."""
    return (
        cq.Workplane("XY")
        .box(
            config.base_length,
            config.base_width,
            config.base_height,
            centered=(True, True, False),
        )
    )


def _make_tower(
    config: RetractionTowerConfig,
    height: float,
    x_offset: float,
) -> cq.Workplane:
    """Create a single cylindrical tower at the given X offset.

    The cylinder is built on the XY plane and translated so that its
    base sits at ``Z = base_height`` (on top of the base plate).
    """
    radius = config.tower_diameter / 2.0
    return (
        cq.Workplane("XY")
        .circle(radius)
        .extrude(height)
        .translate((x_offset, 0, config.base_height))
    )


def _make_retraction_towers(config: RetractionTowerConfig) -> cq.Workplane:
    """Build the complete two-tower model: base plate + two cylinders."""
    tower_height = config.num_levels * config.level_height
    half_spacing = config.tower_spacing / 2.0

    base = _make_base(config)
    left_tower = _make_tower(config, tower_height, -half_spacing)
    right_tower = _make_tower(config, tower_height, half_spacing)

    return base.union(left_tower).union(right_tower)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_retraction_tower_stl(
    config: RetractionTowerConfig,
    output_path: str,
) -> str:
    """One-shot: build the two-tower model and export to STL.

    Parameters
    ----------
    config:      Tower configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    shape = _make_retraction_towers(config)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
