"""Parametric 3-axis cross model for shrinkage calibration.

Generates three perpendicular rectangular arms (X, Y, Z) meeting at a
centre block, with square window cutouts at regular intervals and
embossed axis labels.  The user prints the specimen, measures each arm
with calipers, and calculates per-axis shrinkage.

All dimensions are in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_shrinkage_cross_stl() to avoid
# loading the heavy OCCT/casadi native libraries at module-import time.
cq: Any = None  # populated by _ensure_cq()


def _stub_casadi() -> None:
    """Provide a stub ``casadi`` package when the real one is not yet loaded.

    cadquery unconditionally imports casadi for its assembly constraint
    solver, but this project uses only basic geometry operations and never
    invokes the solver.  On Windows PyInstaller bundles the casadi native
    DLL (``_casadi.pyd``) is typically missing.  Injecting a lightweight
    stub lets cadquery import cleanly.
    """
    import sys

    if "casadi" not in sys.modules:
        import types

        _fake = types.ModuleType("casadi")
        _fake.__path__ = []  # type: ignore[attr-defined]
        sys.modules["casadi"] = _fake
        sys.modules["casadi.casadi"] = _fake


def _ensure_cq() -> None:
    """Import cadquery on first use and cache in module globals."""
    global cq  # noqa: PLW0603
    if cq is None:
        _stub_casadi()
        import cadquery as _cq

        cq = _cq

# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

ARM_LENGTH = 100.0  # mm — default length of each arm
ARM_SIZE = 10.0     # mm — cross-section of each arm (square)
WINDOW_SIZE = 5.0   # mm — side length of square window cutouts
WINDOW_INTERVAL = 20.0  # mm — spacing between window cutout centres
LABEL_DEPTH = 0.6   # mm — embossed text depth
LABEL_FONT_SIZE = 6.0  # mm — font size for axis labels


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class ShrinkageCrossConfig:
    """Parameters for the shrinkage calibration cross.

    Attributes
    ----------
    arm_length:     Length of each arm in mm.
    arm_size:       Cross-section side length of each arm in mm.
    filament_type:  Label for filament type (e.g. ``"ABS"``).
    """

    arm_length: float = ARM_LENGTH
    arm_size: float = ARM_SIZE
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_cross(config: ShrinkageCrossConfig) -> cq.Workplane:
    """Build a 3-axis cross with window cutouts and axis labels.

    The cross is composed of three perpendicular rectangular arms:

    * **X arm** — lies along the X-axis.
    * **Y arm** — lies along the Y-axis.
    * **Z arm** — stands vertical.

    All arms share the same square cross-section (*arm_size* × *arm_size*)
    and meet at a centre block.  Square window cutouts are punched through
    each arm at regular intervals, and ``X``/``Y``/``Z`` labels are
    embossed near each arm's positive end.
    """
    length = config.arm_length
    size = config.arm_size
    half = size / 2.0

    # --- Build the three arms -------------------------------------------
    # X arm: centred on X-axis, lying flat at Y=[-half..+half], Z=[0..size]
    x_arm = (
        cq.Workplane("XY")
        .box(length, size, size, centered=False)
    )

    # Y arm: centred on Y-axis, lying flat at X=[length/2 - half .. length/2 + half]
    y_arm = (
        cq.Workplane("XY")
        .transformed(offset=(length / 2.0 - half, -(length / 2.0 - half), 0))
        .box(size, length, size, centered=False)
    )

    # Z arm: vertical column
    z_arm = (
        cq.Workplane("XY")
        .transformed(offset=(length / 2.0 - half, 0, 0))
        .box(size, size, length, centered=False)
    )

    cross = x_arm.union(y_arm).union(z_arm)

    # --- Window cutouts -------------------------------------------------
    # Cut square through-holes at regular intervals along each arm.
    # Skip positions that fall inside the centre intersection region.
    centre_lo = length / 2.0 - half
    centre_hi = length / 2.0 + half

    win = WINDOW_SIZE
    interval = WINDOW_INTERVAL

    for pos in _window_positions(length, interval, centre_lo, centre_hi):
        # X arm windows: cut through the arm in the Y direction.
        # XZ workplane: offset=(a,b,c) → global (a, -c, b), extrude → -Y.
        # Arm occupies Y=[0,size], Z=[0,size].  Place rect at Z-centre
        # (b=half) and start at Y=size (c=-size) so extrude(size) reaches Y=0.
        cross = cross.cut(
            cq.Workplane("XZ")
            .transformed(offset=(pos, half, -size))
            .rect(win, win)
            .extrude(size)
        )

    for pos in _window_positions(length, interval, centre_lo, centre_hi):
        # Y arm windows: cut through X-axis at the Y arm's X position.
        # YZ workplane local coords: (globalY, globalZ, globalX).
        y_offset = -(length / 2.0 - half) + pos
        cross = cross.cut(
            cq.Workplane("YZ")
            .transformed(offset=(y_offset, half, length / 2.0 - half))
            .rect(win, win)
            .extrude(size)
        )

    for pos in _window_positions(length, interval, centre_lo, centre_hi):
        # Z arm windows: cut through the arm in the Y direction.
        # XZ workplane: offset=(a,b,c) → global (a, -c, b), extrude → -Y.
        # Arm occupies X=[length/2-half, length/2+half], Y=[0,size], Z=[0,length].
        # Place rect at X-centre (a=length/2), Z=pos (b=pos), start at
        # Y=size (c=-size) so extrude(size) reaches Y=0.
        cross = cross.cut(
            cq.Workplane("XZ")
            .transformed(offset=(length / 2.0, pos, -size))
            .rect(win, win)
            .extrude(size)
        )

    # --- Axis labels ----------------------------------------------------
    font = LABEL_FONT_SIZE
    depth = LABEL_DEPTH
    label_offset = length - size  # near the positive end

    # X label — on the top face of the X arm, near positive X end
    x_label = (
        cq.Workplane("XY")
        .workplane(offset=size)
        .center(label_offset, half)
        .text("X", font, depth, combine=False, halign="center", valign="center")
    )
    cross = cross.union(x_label)

    # Y label — on the top face of the Y arm, near positive Y end
    y_label = (
        cq.Workplane("XY")
        .workplane(offset=size)
        .center(length / 2.0, length / 2.0 - half - size)
        .text("Y", font, depth, combine=False, halign="center", valign="center")
    )
    cross = cross.union(y_label)

    # Z label — on the front face of the Z arm, near the top
    z_label = (
        cq.Workplane("XZ")
        .workplane(offset=0)
        .center(length / 2.0, label_offset)
        .text("Z", font, depth, combine=False, halign="center", valign="center")
    )
    cross = cross.union(z_label)

    return cross


def _window_positions(
    arm_length: float,
    interval: float,
    centre_lo: float,
    centre_hi: float,
) -> list[float]:
    """Return a list of centre positions for window cutouts along an arm.

    Positions start at *interval* and repeat every *interval* up to
    *arm_length*.  Positions that fall inside the centre intersection
    region ``[centre_lo, centre_hi]`` are skipped.
    """
    positions: list[float] = []
    pos = interval
    while pos < arm_length:
        if pos < centre_lo or pos > centre_hi:
            positions.append(pos)
        pos += interval
    return positions


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_shrinkage_cross_stl(
    config: ShrinkageCrossConfig,
    output_path: str,
) -> str:
    """One-shot: build the shrinkage cross and export to STL.

    Parameters
    ----------
    config:      Cross configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    shape = _make_cross(config)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
