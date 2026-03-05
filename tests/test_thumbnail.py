"""Tests for filament_calibrator.thumbnail — STL rendering and bgcode injection."""
from __future__ import annotations

import io
import struct
import warnings
import zlib
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

import gcode_lib as gl

from filament_calibrator.thumbnail import (
    ThumbnailSpec,
    _BLK_THUMBNAIL,
    _COMP_NONE,
    _IMG_PNG,
    _SUPERSAMPLE_FACTOR,
    _SUPERSAMPLE_THRESHOLD,
    build_thumbnail_block,
    inject_thumbnails,
    parse_thumbnail_specs,
    render_stl_to_png,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_binary_stl(vertices_list: list[list[tuple[float, float, float]]]) -> bytes:
    """Create minimal binary STL bytes from triangles.

    *vertices_list* is a list of triangles, each a list of 3 (x, y, z) tuples.
    Normals are set to (0, 0, 1) for simplicity.
    """
    buf = io.BytesIO()
    buf.write(b"\x00" * 80)  # header
    buf.write(struct.pack("<I", len(vertices_list)))
    for tri in vertices_list:
        # normal
        buf.write(struct.pack("<3f", 0.0, 0.0, 1.0))
        for v in tri:
            buf.write(struct.pack("<3f", *v))
        buf.write(struct.pack("<H", 0))  # attribute byte count
    return buf.getvalue()


def _make_stl_file(tmp_path, triangles=None):
    """Write a simple binary STL file and return its path."""
    if triangles is None:
        # A simple 10×10×5 box (two triangles for top face — enough to render).
        triangles = [
            [(0, 0, 0), (10, 0, 0), (10, 10, 0)],
            [(0, 0, 0), (10, 10, 0), (0, 10, 0)],
            [(0, 0, 5), (10, 0, 5), (10, 10, 5)],
            [(0, 0, 5), (10, 10, 5), (0, 10, 5)],
        ]
    stl_path = tmp_path / "test_model.stl"
    stl_path.write_bytes(_make_binary_stl(triangles))
    return str(stl_path)


def _make_png_bytes(width: int = 4, height: int = 4) -> bytes:
    """Create minimal valid PNG bytes."""
    img = Image.new("RGB", (width, height), color=(237, 107, 33))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# parse_thumbnail_specs
# ---------------------------------------------------------------------------


class TestParseThumbnailSpecs:
    def test_default_spec(self):
        specs = parse_thumbnail_specs("16x16/PNG,220x124/PNG")
        assert len(specs) == 2
        assert specs[0] == ThumbnailSpec(width=16, height=16)
        assert specs[1] == ThumbnailSpec(width=220, height=124)

    def test_single_spec(self):
        specs = parse_thumbnail_specs("220x124/PNG")
        assert len(specs) == 1
        assert specs[0].width == 220
        assert specs[0].height == 124

    def test_no_format_suffix(self):
        specs = parse_thumbnail_specs("100x80")
        assert len(specs) == 1
        assert specs[0] == ThumbnailSpec(width=100, height=80)

    def test_empty_string(self):
        assert parse_thumbnail_specs("") == []

    def test_whitespace_only(self):
        assert parse_thumbnail_specs("   ") == []

    def test_invalid_format_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            specs = parse_thumbnail_specs("bad")
            assert specs == []
            assert len(w) == 1
            assert "invalid thumbnail spec" in str(w[0].message).lower()

    def test_non_numeric_warns(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            specs = parse_thumbnail_specs("axb/PNG")
            assert specs == []
            assert len(w) == 1

    def test_mixed_valid_invalid(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            specs = parse_thumbnail_specs("16x16/PNG,bad,220x124/PNG")
            assert len(specs) == 2
            assert len(w) == 1

    def test_trailing_comma(self):
        specs = parse_thumbnail_specs("16x16/PNG,")
        assert len(specs) == 1


# ---------------------------------------------------------------------------
# build_thumbnail_block
# ---------------------------------------------------------------------------


class TestBuildThumbnailBlock:
    def test_block_structure(self):
        png = _make_png_bytes(16, 16)
        block = build_thumbnail_block(png, 16, 16)

        # Header: type(2) + compression(2) + uncompressed_size(4) = 8 bytes
        btype, comp, size = struct.unpack_from("<HHI", block, 0)
        assert btype == _BLK_THUMBNAIL
        assert comp == _COMP_NONE
        assert size == len(png)

        # Params: width(2) + height(2) + format(2) = 6 bytes
        w, h, fmt = struct.unpack_from("<HHH", block, 8)
        assert w == 16
        assert h == 16
        assert fmt == _IMG_PNG

        # Payload
        payload = block[14 : 14 + len(png)]
        assert payload == png

        # CRC32 (4 bytes at the end)
        assert len(block) == 8 + 6 + len(png) + 4

    def test_crc32_valid(self):
        png = _make_png_bytes(220, 124)
        block = build_thumbnail_block(png, 220, 124)

        payload_end = len(block) - 4
        stored_crc = struct.unpack_from("<I", block, payload_end)[0]
        computed_crc = zlib.crc32(block[:payload_end]) & 0xFFFFFFFF
        assert computed_crc == stored_crc

    def test_dimensions_in_params(self):
        png = _make_png_bytes(100, 80)
        block = build_thumbnail_block(png, 100, 80)

        w, h, fmt = struct.unpack_from("<HHH", block, 8)
        assert (w, h, fmt) == (100, 80, _IMG_PNG)


# ---------------------------------------------------------------------------
# render_stl_to_png
# ---------------------------------------------------------------------------


class TestRenderStlToPng:
    def test_returns_valid_png(self, tmp_path):
        stl = _make_stl_file(tmp_path)
        png = render_stl_to_png(stl, 64, 64)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_correct_dimensions(self, tmp_path):
        stl = _make_stl_file(tmp_path)
        png = render_stl_to_png(stl, 220, 124)
        img = Image.open(io.BytesIO(png))
        assert img.size == (220, 124)

    def test_small_thumbnail_supersample(self, tmp_path):
        stl = _make_stl_file(tmp_path)
        png = render_stl_to_png(stl, 16, 16)
        img = Image.open(io.BytesIO(png))
        assert img.size == (16, 16)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            render_stl_to_png(str(tmp_path / "nonexistent.stl"), 64, 64)

    @patch("filament_calibrator.thumbnail._HAS_VTK", False)
    def test_no_vtk_raises_runtime_error(self, tmp_path):
        stl = _make_stl_file(tmp_path)
        with pytest.raises(RuntimeError, match="VTK is not installed"):
            render_stl_to_png(stl, 64, 64)

    def test_large_thumbnail_no_supersample(self, tmp_path):
        stl = _make_stl_file(tmp_path)
        png = render_stl_to_png(stl, 100, 80)
        img = Image.open(io.BytesIO(png))
        assert img.size == (100, 80)


# ---------------------------------------------------------------------------
# inject_thumbnails
# ---------------------------------------------------------------------------


class TestInjectThumbnails:
    def _make_gf(self, source_format="bgcode"):
        """Create a minimal GCodeFile mock."""
        gf = gl.GCodeFile(
            lines=[],
            thumbnails=[],
            source_format=source_format,
        )
        if source_format == "bgcode":
            gf._bgcode_file_hdr = b"GCDE" + struct.pack("<I", 1) + struct.pack("<H", 1)
            gf._bgcode_nongcode_blocks = []
        return gf

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_bgcode_injection(self, mock_render, tmp_path):
        png_data = _make_png_bytes(16, 16)
        mock_render.return_value = png_data
        stl = _make_stl_file(tmp_path)

        gf = self._make_gf("bgcode")
        inject_thumbnails(gf, stl, "16x16/PNG")

        assert len(gf.thumbnails) == 1
        assert gf.thumbnails[0].width == 16
        assert gf.thumbnails[0].height == 16
        assert gf.thumbnails[0].data == png_data
        assert len(gf._bgcode_nongcode_blocks) == 1

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_multiple_sizes(self, mock_render, tmp_path):
        png16 = _make_png_bytes(16, 16)
        png220 = _make_png_bytes(220, 124)
        mock_render.side_effect = [png16, png220]
        stl = _make_stl_file(tmp_path)

        gf = self._make_gf("bgcode")
        inject_thumbnails(gf, stl, "16x16/PNG,220x124/PNG")

        assert len(gf.thumbnails) == 2
        assert len(gf._bgcode_nongcode_blocks) == 2
        assert gf.thumbnails[0].width == 16
        assert gf.thumbnails[1].width == 220

    def test_ascii_gcode_skipped(self, tmp_path):
        gf = self._make_gf("text")
        stl = _make_stl_file(tmp_path)
        inject_thumbnails(gf, stl, "16x16/PNG")
        assert len(gf.thumbnails) == 0

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_already_has_thumbnails_skipped(self, mock_render, tmp_path):
        gf = self._make_gf("bgcode")
        gf.thumbnails.append(
            gl.Thumbnail(
                params=struct.pack("<HHH", 16, 16, 0),
                data=b"existing",
                _raw_block=b"",
            )
        )
        stl = _make_stl_file(tmp_path)
        inject_thumbnails(gf, stl, "16x16/PNG")
        mock_render.assert_not_called()

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_render_failure_warns(self, mock_render, tmp_path):
        mock_render.side_effect = RuntimeError("render failed")
        stl = _make_stl_file(tmp_path)

        gf = self._make_gf("bgcode")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            inject_thumbnails(gf, stl, "16x16/PNG")
            assert len(w) == 1
            assert "render failed" in str(w[0].message)
        assert len(gf.thumbnails) == 0

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_verbose_output(self, mock_render, tmp_path, capsys):
        mock_render.return_value = _make_png_bytes(16, 16)
        stl = _make_stl_file(tmp_path)

        gf = self._make_gf("bgcode")
        inject_thumbnails(gf, stl, "16x16/PNG", verbose=True)

        captured = capsys.readouterr()
        assert "Rendering 16" in captured.out
        assert "Injected 1" in captured.out

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_verbose_already_present(self, mock_render, tmp_path, capsys):
        gf = self._make_gf("bgcode")
        gf.thumbnails.append(
            gl.Thumbnail(
                params=struct.pack("<HHH", 16, 16, 0),
                data=b"existing",
                _raw_block=b"",
            )
        )
        stl = _make_stl_file(tmp_path)
        inject_thumbnails(gf, stl, "16x16/PNG", verbose=True)

        captured = capsys.readouterr()
        assert "already present" in captured.out.lower()

    def test_empty_spec_skipped(self, tmp_path):
        gf = self._make_gf("bgcode")
        stl = _make_stl_file(tmp_path)
        inject_thumbnails(gf, stl, "")
        assert len(gf.thumbnails) == 0

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_prepends_before_existing_blocks(self, mock_render, tmp_path):
        mock_render.return_value = _make_png_bytes(16, 16)
        stl = _make_stl_file(tmp_path)

        gf = self._make_gf("bgcode")
        existing_block = b"existing_metadata_block"
        gf._bgcode_nongcode_blocks.append(existing_block)

        inject_thumbnails(gf, stl, "16x16/PNG")

        assert len(gf._bgcode_nongcode_blocks) == 2
        # Thumbnail block should come BEFORE the existing block.
        assert gf._bgcode_nongcode_blocks[1] == existing_block
        assert gf._bgcode_nongcode_blocks[0] != existing_block


# ---------------------------------------------------------------------------
# Integration: round-trip with gcode-lib
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Verify that injected thumbnails survive a save → load cycle."""

    @patch("filament_calibrator.thumbnail.render_stl_to_png")
    def test_save_load_preserves_thumbnails(self, mock_render, tmp_path):
        png16 = _make_png_bytes(16, 16)
        png220 = _make_png_bytes(220, 124)
        mock_render.side_effect = [png16, png220]
        stl = _make_stl_file(tmp_path)

        # Build a minimal valid bgcode GCodeFile.
        gf = gl.GCodeFile(
            lines=gl.parse_lines("G28 ; home\n"),
            thumbnails=[],
            source_format="bgcode",
            _bgcode_file_hdr=b"GCDE" + struct.pack("<IH", 1, 1),
            _bgcode_nongcode_blocks=[],
        )
        inject_thumbnails(gf, stl, "16x16/PNG,220x124/PNG")
        assert len(gf.thumbnails) == 2

        # Save and reload.
        out_path = str(tmp_path / "test.bgcode")
        gl.save(gf, out_path)

        gf2 = gl.load(out_path)
        assert gf2.source_format == "bgcode"
        assert len(gf2.thumbnails) == 2
        assert gf2.thumbnails[0].width == 16
        assert gf2.thumbnails[0].height == 16
        assert gf2.thumbnails[1].width == 220
        assert gf2.thumbnails[1].height == 124
        assert gf2.thumbnails[0].data == png16
        assert gf2.thumbnails[1].data == png220
