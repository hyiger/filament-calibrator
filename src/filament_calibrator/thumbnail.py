"""Thumbnail rendering and injection for binary G-code files.

Renders an STL model to PNG images at specified sizes and injects them
as bgcode thumbnail blocks into a GCodeFile.  Rendering failures are
non-fatal: a warning is printed and the pipeline continues without
thumbnails.
"""
from __future__ import annotations

import io
import struct
import warnings
import zlib
from dataclasses import dataclass
from typing import List

import gcode_lib as gl

# ---------------------------------------------------------------------------
# bgcode block constants (matching gcode_lib internals)
# ---------------------------------------------------------------------------

_BLK_THUMBNAIL: int = 5
_COMP_NONE: int = 0
_IMG_PNG: int = 0

# ---------------------------------------------------------------------------
# VTK availability
# ---------------------------------------------------------------------------

try:
    import vtk as _vtk  # type: ignore[import-untyped]

    _HAS_VTK = True
except ImportError:  # pragma: no cover
    _vtk = None  # type: ignore[assignment]
    _HAS_VTK = False

# ---------------------------------------------------------------------------
# Rendering constants
# ---------------------------------------------------------------------------

# PrusaSlicer default filament colour (#ED6B21) as normalised RGB floats.
_MODEL_COLOR = (0.93, 0.42, 0.13)

# Small thumbnails (≤32 px) are rendered at this multiple then downscaled
# for better visual quality.
_SUPERSAMPLE_THRESHOLD: int = 32
_SUPERSAMPLE_FACTOR: int = 4


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ThumbnailSpec:
    """Desired thumbnail size and format."""

    width: int
    height: int


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def parse_thumbnail_specs(spec: str) -> List[ThumbnailSpec]:
    """Parse a PrusaSlicer-style thumbnail spec string.

    >>> parse_thumbnail_specs("16x16/PNG,220x124/PNG")
    [ThumbnailSpec(width=16, height=16), ThumbnailSpec(width=220, height=124)]
    """
    if not spec or not spec.strip():
        return []
    specs: List[ThumbnailSpec] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        # Accept "WxH/FMT" or "WxH"
        size_part = part.split("/")[0]
        dims = size_part.lower().split("x")
        if len(dims) != 2:
            warnings.warn(f"Skipping invalid thumbnail spec: {part!r}")
            continue
        try:
            w, h = int(dims[0]), int(dims[1])
        except ValueError:
            warnings.warn(f"Skipping invalid thumbnail spec: {part!r}")
            continue
        specs.append(ThumbnailSpec(width=w, height=h))
    return specs


def render_stl_to_png(stl_path: str, width: int, height: int) -> bytes:
    """Render a binary STL file to PNG bytes at the requested size.

    Uses VTK off-screen rendering with an isometric-ish camera view and
    PrusaSlicer-orange model colouring.

    Raises
    ------
    RuntimeError
        If VTK is not available.
    FileNotFoundError
        If *stl_path* does not exist.
    """
    if not _HAS_VTK:
        raise RuntimeError("VTK is not installed; cannot render thumbnails")

    import pathlib

    if not pathlib.Path(stl_path).exists():
        raise FileNotFoundError(stl_path)

    # Determine render size (supersample small thumbnails).
    if width <= _SUPERSAMPLE_THRESHOLD or height <= _SUPERSAMPLE_THRESHOLD:
        render_w = width * _SUPERSAMPLE_FACTOR
        render_h = height * _SUPERSAMPLE_FACTOR
        needs_downscale = True
    else:
        render_w = width
        render_h = height
        needs_downscale = False

    return _render_vtk(stl_path, render_w, render_h, width, height, needs_downscale)


def build_thumbnail_block(png_data: bytes, width: int, height: int) -> bytes:
    """Construct a raw bgcode thumbnail block from PNG image data.

    The returned bytes are suitable for inserting into
    ``GCodeFile._bgcode_nongcode_blocks``.
    """
    hdr = struct.pack("<HHI", _BLK_THUMBNAIL, _COMP_NONE, len(png_data))
    params = struct.pack("<HHH", width, height, _IMG_PNG)
    cksum = zlib.crc32(hdr) & 0xFFFFFFFF
    cksum = zlib.crc32(params, cksum) & 0xFFFFFFFF
    cksum = zlib.crc32(png_data, cksum) & 0xFFFFFFFF
    return hdr + params + png_data + struct.pack("<I", cksum)


def inject_thumbnails(
    gf: gl.GCodeFile,
    stl_path: str,
    spec_string: str,
    *,
    verbose: bool = False,
) -> None:
    """Inject rendered thumbnails into a binary G-code file.

    Does nothing for ASCII G-code or if thumbnails are already present.
    Failures are non-fatal: a warning is issued and the pipeline continues.
    """
    if gf.source_format != "bgcode":
        return

    if gf.thumbnails:
        if verbose:
            print("[DEBUG] Thumbnails already present — skipping injection")
        return

    specs = parse_thumbnail_specs(spec_string)
    if not specs:
        return

    try:
        new_blocks: list[bytes] = []
        new_thumbs: list[gl.Thumbnail] = []

        for spec in specs:
            if verbose:
                print(
                    f"[DEBUG] Rendering {spec.width}×{spec.height} "
                    f"thumbnail from {stl_path}"
                )
            png_data = render_stl_to_png(stl_path, spec.width, spec.height)
            block = build_thumbnail_block(png_data, spec.width, spec.height)
            params = struct.pack("<HHH", spec.width, spec.height, _IMG_PNG)
            new_blocks.append(block)
            new_thumbs.append(
                gl.Thumbnail(params=params, data=png_data, _raw_block=block)
            )

        # Prepend thumbnail blocks (convention: thumbnails before metadata).
        if gf._bgcode_nongcode_blocks is None:
            gf._bgcode_nongcode_blocks = []  # pragma: no cover
        gf._bgcode_nongcode_blocks[:0] = new_blocks
        gf.thumbnails.extend(new_thumbs)

        if verbose:
            print(f"[DEBUG] Injected {len(new_thumbs)} thumbnail(s)")

    except Exception as exc:
        warnings.warn(f"Thumbnail injection failed: {exc}")


# ---------------------------------------------------------------------------
# Private — VTK rendering pipeline
# ---------------------------------------------------------------------------


def _render_vtk(
    stl_path: str,
    render_w: int,
    render_h: int,
    final_w: int,
    final_h: int,
    needs_downscale: bool,
) -> bytes:
    """Render an STL file to PNG bytes using VTK off-screen rendering."""
    # --- Read STL ---
    reader = _vtk.vtkSTLReader()
    reader.SetFileName(stl_path)
    reader.Update()

    # --- Mapper + Actor ---
    mapper = _vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(reader.GetOutputPort())

    actor = _vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*_MODEL_COLOR)
    actor.GetProperty().SetAmbient(0.3)
    actor.GetProperty().SetDiffuse(0.7)

    # --- Renderer ---
    renderer = _vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.SetBackground(0.22, 0.22, 0.22)

    # --- Render window (off-screen) ---
    window = _vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(render_w, render_h)
    window.AddRenderer(renderer)

    # --- Camera: isometric-ish view with Z-up (matching 3D-print bed) ---
    renderer.ResetCamera()
    camera = renderer.GetActiveCamera()
    # Position camera at front-right, looking slightly down — the same
    # angle PrusaSlicer uses for its LCD preview thumbnails.
    focal = list(camera.GetFocalPoint())
    dist = camera.GetDistance()
    import math

    az = math.radians(35)   # front-right, text labels facing camera
    el = math.radians(25)   # 25 ° above the horizon
    camera.SetPosition(
        focal[0] + dist * math.cos(el) * math.sin(az),
        focal[1] - dist * math.cos(el) * math.cos(az),
        focal[2] + dist * math.sin(el),
    )
    camera.SetViewUp(0, 0, 1)
    renderer.ResetCameraClippingRange()

    window.Render()

    # --- Capture image ---
    w2i = _vtk.vtkWindowToImageFilter()
    w2i.SetInput(window)
    w2i.Update()

    # --- Downscale if supersampled ---
    if needs_downscale:
        resizer = _vtk.vtkImageResize()
        resizer.SetInputConnection(w2i.GetOutputPort())
        resizer.SetOutputDimensions(final_w, final_h, 1)
        resizer.Update()
        source = resizer.GetOutputPort()
    else:
        source = w2i.GetOutputPort()

    # --- Write PNG to memory ---
    writer = _vtk.vtkPNGWriter()
    writer.WriteToMemoryOn()
    writer.SetInputConnection(source)
    writer.Write()

    # Get bytes from the vtkUnsignedCharArray result.
    result = writer.GetResult()
    png_bytes = bytes(
        result.GetValue(i) for i in range(result.GetNumberOfTuples())
    )

    # Clean up.
    window.Finalize()

    return png_bytes
