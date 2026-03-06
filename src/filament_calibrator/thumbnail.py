"""Thumbnail rendering and injection for binary G-code files.

Renders an STL model to PNG images at specified sizes and injects them
as bgcode thumbnail blocks into a GCodeFile.  Rendering failures are
non-fatal: a warning is printed and the pipeline continues without
thumbnails.
"""
from __future__ import annotations

import multiprocessing as mp
import platform
import struct
import warnings
import zlib
from dataclasses import dataclass
from typing import List

import gcode_lib as gl

# ---------------------------------------------------------------------------
# bgcode block constants (matching gcode_lib internals)
# ---------------------------------------------------------------------------

_BLK_FILE_METADATA: int = 0
_BLK_SLICER_METADATA: int = 2
_BLK_PRINTER_METADATA: int = 3
_BLK_PRINT_METADATA: int = 4
_BLK_THUMBNAIL: int = 5
_COMP_NONE: int = 0
_COMP_DEFLATE: int = 1
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


def _fallback_png(width: int, height: int) -> bytes:
    """Return a minimal solid-color RGB PNG as a safe rendering fallback."""
    # PNG requires positive dimensions.
    w = max(1, int(width))
    h = max(1, int(height))

    # Convert the model color (0..1 floats) to 8-bit RGB.
    r = max(0, min(255, int(round(_MODEL_COLOR[0] * 255))))
    g = max(0, min(255, int(round(_MODEL_COLOR[1] * 255))))
    b = max(0, min(255, int(round(_MODEL_COLOR[2] * 255))))

    # Each scanline: filter byte (0) + RGB triplets.
    row = bytes([0]) + bytes([r, g, b]) * w
    raw = row * h

    def _chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(raw)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


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

    On macOS, VTK's Cocoa render window must be created on the main
    thread.  When called from a non-main thread (e.g. a Streamlit worker),
    this function transparently offloads rendering to a subprocess.

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

    if _needs_subprocess_render():
        try:
            return _render_in_subprocess(
                stl_path, render_w, render_h, width, height, needs_downscale,
            )
        except RuntimeError as exc:
            warnings.warn(
                f"VTK subprocess render failed ({exc}); using fallback thumbnail"
            )
            return _fallback_png(width, height)
    return _render_vtk(stl_path, render_w, render_h, width, height, needs_downscale)


def build_thumbnail_block(png_data: bytes, width: int, height: int) -> bytes:
    """Construct a raw bgcode thumbnail block from PNG image data.

    The returned bytes are suitable for inserting into
    ``GCodeFile._bgcode_nongcode_blocks``.

    The 6-byte params field follows the libbgcode spec order:
    ``format (u16) | width (u16) | height (u16)``.
    """
    hdr = struct.pack("<HHI", _BLK_THUMBNAIL, _COMP_NONE, len(png_data))
    params = struct.pack("<HHH", _IMG_PNG, width, height)
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
            # gcode_lib's Thumbnail.params uses width,height,format order
            # for .width/.height properties (differs from the bgcode spec's
            # format,width,height in the raw block).
            gl_params = struct.pack("<HHH", spec.width, spec.height, _IMG_PNG)
            new_blocks.append(block)
            new_thumbs.append(
                gl.Thumbnail(params=gl_params, data=png_data, _raw_block=block)
            )

        # Insert thumbnail blocks after PRINTER_METADATA (type 3) and
        # before PRINT_METADATA (type 4), matching PrusaSlicer's native
        # block order.
        if gf._bgcode_nongcode_blocks is None:
            gf._bgcode_nongcode_blocks = []  # pragma: no cover
        insert_pos = _find_thumbnail_insert_pos(gf._bgcode_nongcode_blocks)
        for i, blk in enumerate(new_blocks):
            gf._bgcode_nongcode_blocks.insert(insert_pos + i, blk)
        gf.thumbnails.extend(new_thumbs)

        if verbose:
            print(f"[DEBUG] Injected {len(new_thumbs)} thumbnail(s)")

    except Exception as exc:
        warnings.warn(f"Thumbnail injection failed: {exc}")


# ---------------------------------------------------------------------------
# Slicer metadata patching
# ---------------------------------------------------------------------------

# PrusaSlicer G-code Viewer uses ``printer_settings_id`` from the slicer
# metadata block to look up the bed model from its bundled vendor profiles.
# PrusaSlicer CLI leaves this field empty, so we patch it post-slicing.
# Map: (printer_model, nozzle_diameter_str) → printer_settings_id.
_PRINTER_SETTINGS_IDS: dict[tuple[str, str], str] = {
    ("COREONE", "0.25"): "Prusa CORE One 0.25 nozzle",
    ("COREONE", "0.3"):  "Prusa CORE One 0.3 nozzle",
    ("COREONE", "0.4"):  "Prusa CORE One HF0.4 nozzle",
    ("COREONE", "0.5"):  "Prusa CORE One HF0.5 nozzle",
    ("COREONE", "0.6"):  "Prusa CORE One HF0.6 nozzle",
    ("COREONE", "0.8"):  "Prusa CORE One HF0.8 nozzle",
}


def patch_slicer_metadata(
    gf: gl.GCodeFile,
    printer_model: str,
    nozzle_diameter: float,
    *,
    verbose: bool = False,
) -> None:
    """Patch the SLICER_METADATA block to set ``printer_settings_id``.

    PrusaSlicer CLI leaves ``printer_settings_id`` empty in the slicer
    metadata block.  The G-code Viewer needs this field to look up the
    printer bed model from its bundled vendor profiles.  This function
    patches the existing SLICER_METADATA block in-place.

    Does nothing for ASCII G-code or if no matching profile is found.
    Failures are non-fatal.
    """
    if gf.source_format != "bgcode":
        return

    nozzle_str = f"{nozzle_diameter:g}"
    settings_id = _PRINTER_SETTINGS_IDS.get((printer_model, nozzle_str))
    if settings_id is None:
        if verbose:
            print(
                f"[DEBUG] No printer_settings_id mapping for "
                f"({printer_model}, {nozzle_str})"
            )
        return

    blocks = gf._bgcode_nongcode_blocks
    if not blocks:
        return

    try:
        idx = _find_slicer_meta_index(blocks)
        if idx is None:
            return

        old_block = blocks[idx]
        new_block = _rebuild_slicer_meta_block(
            old_block,
            {"printer_settings_id": settings_id},
        )
        blocks[idx] = new_block

        if verbose:
            print(f"[DEBUG] Patched printer_settings_id={settings_id}")

    except Exception as exc:
        warnings.warn(f"Slicer metadata patch failed: {exc}")


def _find_slicer_meta_index(blocks: list[bytes]) -> int | None:
    """Return the index of the SLICER_METADATA block, or ``None``."""
    for i, blk in enumerate(blocks):
        btype = struct.unpack_from("<H", blk, 0)[0]
        if btype == _BLK_SLICER_METADATA:
            return i
    return None


def _rebuild_slicer_meta_block(
    raw_block: bytes,
    updates: dict[str, str],
) -> bytes:
    """Rebuild a SLICER_METADATA block with updated key=value pairs.

    Handles both uncompressed and deflate-compressed blocks.
    """
    btype, comp, usize = struct.unpack_from("<HHI", raw_block, 0)
    assert btype == _BLK_SLICER_METADATA

    if comp == _COMP_NONE:
        # header(8) + params(2) + payload(usize) + crc(4)
        params = raw_block[8:10]
        payload = raw_block[10 : 10 + usize]
    elif comp == _COMP_DEFLATE:
        # header(8) + compressed_size(4) + params(2) + payload(cs) + crc(4)
        cs = struct.unpack_from("<I", raw_block, 8)[0]
        params = raw_block[12:14]
        compressed = raw_block[14 : 14 + cs]
        payload = zlib.decompress(compressed)
    else:
        # Heatshrink or unknown — can't patch, return as-is.
        return raw_block

    # Apply updates to the INI-style text (line-anchored to avoid
    # partial matches like physical_printer_settings_id).
    import re

    text = payload.decode("utf-8")
    for key, value in updates.items():
        pattern = rf"^{re.escape(key)}=.*$"
        if re.search(pattern, text, flags=re.MULTILINE):
            text = re.sub(pattern, f"{key}={value}", text, flags=re.MULTILINE)
        else:
            text = text.rstrip("\n") + f"\n{key}={value}\n"

    new_payload = text.encode("utf-8")

    # Rebuild the block.
    new_hdr = struct.pack("<HHI", btype, comp, len(new_payload))
    if comp == _COMP_DEFLATE:
        new_compressed = zlib.compress(new_payload)
        cs_bytes = struct.pack("<I", len(new_compressed))
        block_body = new_hdr + cs_bytes + params + new_compressed
    else:
        block_body = new_hdr + params + new_payload

    crc = struct.pack("<I", zlib.crc32(block_body) & 0xFFFFFFFF)
    return block_body + crc


# ---------------------------------------------------------------------------
# Private — block ordering
# ---------------------------------------------------------------------------


def _find_thumbnail_insert_pos(blocks: list[bytes]) -> int:
    """Return the index at which thumbnail blocks should be inserted.

    PrusaSlicer orders blocks as FILE_METADATA → PRINTER_METADATA →
    THUMBNAIL(s) → PRINT_METADATA → SLICER_METADATA.  We insert after
    the last FILE_METADATA or PRINTER_METADATA block (types 0 and 3).
    """
    pos = 0
    for i, blk in enumerate(blocks):
        btype = struct.unpack_from("<H", blk, 0)[0]
        if btype in (_BLK_FILE_METADATA, _BLK_PRINTER_METADATA):
            pos = i + 1
    return pos


# ---------------------------------------------------------------------------
# Private — macOS thread-safety helpers
# ---------------------------------------------------------------------------


def _needs_subprocess_render() -> bool:
    """Return ``True`` if VTK rendering must be offloaded to a subprocess.

    On macOS, VTK creates a ``vtkCocoaRenderWindow`` which calls into
    AppKit (``NSWindow``).  AppKit requires all UI operations on the main
    thread, and in-process offscreen rendering can still abort in some
    environments (for example test runners).  Always render in a subprocess
    on Darwin to isolate potential native crashes.
    """
    return platform.system() == "Darwin"


def _subprocess_render_worker(
    result_queue: object,
    stl_path: str,
    render_w: int,
    render_h: int,
    final_w: int,
    final_h: int,
    needs_downscale: bool,
) -> None:
    """Multiprocessing worker that runs ``_render_vtk`` on the main thread."""
    try:
        png = _render_vtk(stl_path, render_w, render_h, final_w, final_h, needs_downscale)
        result_queue.put(("ok", png))
    except Exception as exc:
        result_queue.put(("error", str(exc)))


def _render_in_subprocess(
    stl_path: str,
    render_w: int,
    render_h: int,
    final_w: int,
    final_h: int,
    needs_downscale: bool,
) -> bytes:
    """Spawn a subprocess to perform VTK rendering on its main thread."""
    ctx = mp.get_context("spawn")
    result_queue: mp.Queue[tuple[str, bytes | str]] = ctx.Queue()

    proc = ctx.Process(
        target=_subprocess_render_worker,
        args=(result_queue, stl_path, render_w, render_h, final_w, final_h, needs_downscale),
    )
    proc.start()
    proc.join(timeout=120)

    if proc.exitcode is None:
        proc.kill()
        raise RuntimeError("VTK render subprocess timed out")

    if proc.exitcode != 0:
        raise RuntimeError(
            f"VTK render subprocess failed (exit code {proc.exitcode})"
        )

    status, data = result_queue.get_nowait()
    if status == "error":
        raise RuntimeError(f"VTK render failed in subprocess: {data}")
    return data  # type: ignore[return-value]


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
