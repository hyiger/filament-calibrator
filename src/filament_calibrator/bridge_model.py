"""Parametric bridge test model for bridging calibration.

Generates a row of pillar pairs along the X axis, each pair connected by
a flat bridge at the top.  Each pair has a different span (gap) distance
between the pillar inner edges.  The user prints the specimen, inspects
the underside of each bridge, and identifies the maximum span length the
printer can bridge cleanly with the current settings.

All dimensions are in millimetres.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# cadquery is imported lazily inside generate_bridge_stl() to avoid
# loading the heavy OCCT/casadi native libraries at module-import time.
cq: Any = None  # populated by _ensure_cq()

# Stub/lazy-import helpers live in _cq_compat; thin wrappers here keep
# existing call sites and test imports working.
from filament_calibrator._cq_compat import ensure_cq as _ensure_cq_impl
from filament_calibrator._cq_compat import stub_casadi as _stub_casadi


def _ensure_cq() -> None:
    """Import cadquery on first use and cache in module globals."""
    global cq  # noqa: PLW0603
    if cq is None:
        cq = _ensure_cq_impl()

# ---------------------------------------------------------------------------
# Geometry constants
# ---------------------------------------------------------------------------

PILLAR_WIDTH: float = 5.0
"""X width of each pillar in mm."""

PILLAR_DEPTH: float = 10.0
"""Y depth of each pillar in mm."""

PILLAR_HEIGHT: float = 15.0
"""Z height of pillars in mm."""

BRIDGE_THICKNESS: float = 2.0
"""Z thickness of the bridge surface in mm."""

BASE_HEIGHT: float = 1.0
"""Base plate height in mm (for bed adhesion)."""

BASE_MARGIN: float = 5.0
"""Margin around outermost pillars on the base plate in mm."""

DEFAULT_SPANS: tuple[float, ...] = (10.0, 20.0, 30.0, 40.0, 50.0, 60.0)
"""Default gap widths between pillar inner edges in mm."""


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class BridgeTestConfig:
    """Parameters for the bridge calibration test model.

    Attributes
    ----------
    spans:            Gap widths between pillar inner edges in mm.
    pillar_width:     X width of each pillar in mm.
    pillar_depth:     Y depth of each pillar in mm.
    pillar_height:    Z height of pillars in mm.
    bridge_thickness: Z thickness of the bridge surface in mm.
    base_height:      Base plate height in mm.
    base_margin:      Margin around outermost pillars on base in mm.
    filament_type:    Label for filament type (e.g. ``"PLA"``).
    """

    spans: tuple[float, ...] = DEFAULT_SPANS
    pillar_width: float = PILLAR_WIDTH
    pillar_depth: float = PILLAR_DEPTH
    pillar_height: float = PILLAR_HEIGHT
    bridge_thickness: float = BRIDGE_THICKNESS
    base_height: float = BASE_HEIGHT
    base_margin: float = BASE_MARGIN
    filament_type: str = "PLA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def total_height(config: BridgeTestConfig) -> float:
    """Return the total Z height of the model (base + pillar + bridge)."""
    return config.base_height + config.pillar_height + config.bridge_thickness


def _pair_width(config: BridgeTestConfig, span: float) -> float:
    """Return the total X extent of one pillar pair (both pillars + gap)."""
    return span + 2 * config.pillar_width


def _total_pairs_width(config: BridgeTestConfig) -> float:
    """Return the total X extent of all pairs including gaps between them.

    Adjacent pairs are separated by ``pillar_width`` (one pillar-width gap).
    """
    pair_widths = sum(_pair_width(config, s) for s in config.spans)
    num_gaps = len(config.spans) - 1
    return pair_widths + num_gaps * config.pillar_width


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------


def _make_base(config: BridgeTestConfig) -> cq.Workplane:
    """Create the rectangular base plate centred at the XY origin."""
    total_x = _total_pairs_width(config) + 2 * config.base_margin
    total_y = config.pillar_depth + 2 * config.base_margin
    return (
        cq.Workplane("XY")
        .box(total_x, total_y, config.base_height, centered=(True, True, False))
    )


def _make_pillar(config: BridgeTestConfig, x: float, y: float = 0.0) -> cq.Workplane:
    """Create a single rectangular pillar at the given X position.

    The pillar base sits at ``Z = base_height`` (on top of the base plate).
    """
    return (
        cq.Workplane("XY")
        .box(
            config.pillar_width,
            config.pillar_depth,
            config.pillar_height,
            centered=(True, True, False),
        )
        .translate((x, y, config.base_height))
    )


def _make_bridge(
    config: BridgeTestConfig,
    x_center: float,
    span: float,
) -> cq.Workplane:
    """Create a flat bridge connecting the tops of a pillar pair.

    The bridge spans from the left pillar's outer edge to the right
    pillar's outer edge at ``Z = base_height + pillar_height``.
    """
    bridge_width = span + 2 * config.pillar_width
    z_bottom = config.base_height + config.pillar_height
    return (
        cq.Workplane("XY")
        .box(
            bridge_width,
            config.pillar_depth,
            config.bridge_thickness,
            centered=(True, True, False),
        )
        .translate((x_center, 0, z_bottom))
    )


def _make_bridge_test(config: BridgeTestConfig) -> cq.Workplane:
    """Build the complete bridge test: base plate + pillar pairs + bridges."""
    result = _make_base(config)

    # Start X at the left edge of the first pair, offset so the
    # overall arrangement is centred at X=0.
    total_w = _total_pairs_width(config)
    x_cursor = -total_w / 2.0

    for span in config.spans:
        pw = _pair_width(config, span)
        x_center = x_cursor + pw / 2.0

        # Left pillar centre: x_center - span/2 - pillar_width/2
        left_x = x_center - span / 2.0 - config.pillar_width / 2.0
        # Right pillar centre: x_center + span/2 + pillar_width/2
        right_x = x_center + span / 2.0 + config.pillar_width / 2.0

        result = result.union(_make_pillar(config, left_x))
        result = result.union(_make_pillar(config, right_x))
        result = result.union(_make_bridge(config, x_center, span))

        # Advance cursor past this pair + inter-pair gap
        x_cursor += pw + config.pillar_width

    return result


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def generate_bridge_stl(
    config: BridgeTestConfig,
    output_path: str,
) -> str:
    """One-shot: build the bridge test model and export to STL.

    Parameters
    ----------
    config:      Bridge test configuration.
    output_path: Where to write the ``.stl`` file.

    Returns
    -------
    str
        The *output_path* (for chaining convenience).
    """
    _ensure_cq()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    shape = _make_bridge_test(config)
    cq.exporters.export(shape, output_path, exportType="STL")
    return output_path
