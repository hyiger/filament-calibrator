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
    _BLK_FILE_METADATA,
    _BLK_PRINTER_METADATA,
    _BLK_PRINT_METADATA,
    _BLK_SLICER_METADATA,
    _BLK_THUMBNAIL,
    _COMP_DEFLATE,
    _COMP_NONE,
    _IMG_PNG,
    _SUPERSAMPLE_FACTOR,
    _SUPERSAMPLE_THRESHOLD,
    _find_slicer_meta_index,
    _find_thumbnail_insert_pos,
    _needs_subprocess_render,
    _rebuild_slicer_meta_block,
    _render_in_subprocess,
    _subprocess_render_worker,
    build_thumbnail_block,
    inject_thumbnails,
    parse_thumbnail_specs,
    patch_slicer_metadata,
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

        # Params per bgcode spec: format(2) + width(2) + height(2) = 6 bytes
        fmt, w, h = struct.unpack_from("<HHH", block, 8)
        assert fmt == _IMG_PNG
        assert w == 16
        assert h == 16

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

        fmt, w, h = struct.unpack_from("<HHH", block, 8)
        assert (fmt, w, h) == (_IMG_PNG, 100, 80)


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
    def test_inserts_after_metadata_blocks(self, mock_render, tmp_path):
        mock_render.return_value = _make_png_bytes(16, 16)
        stl = _make_stl_file(tmp_path)

        gf = self._make_gf("bgcode")
        # Simulate PrusaSlicer block order: FILE_META, PRINTER_META,
        # PRINT_META, SLICER_META.
        file_meta = struct.pack("<HHI", _BLK_FILE_METADATA, 0, 4) + b"test" + b"\x00" * 4
        printer_meta = struct.pack("<HHI", _BLK_PRINTER_METADATA, 0, 4) + b"meta" + b"\x00" * 4
        print_meta = struct.pack("<HHI", _BLK_PRINT_METADATA, 0, 4) + b"prnt" + b"\x00" * 4
        gf._bgcode_nongcode_blocks = [file_meta, printer_meta, print_meta]

        inject_thumbnails(gf, stl, "16x16/PNG")

        assert len(gf._bgcode_nongcode_blocks) == 4
        # Block order should be: FILE_META, PRINTER_META, THUMBNAIL, PRINT_META
        types = [
            struct.unpack_from("<H", b, 0)[0]
            for b in gf._bgcode_nongcode_blocks
        ]
        assert types == [
            _BLK_FILE_METADATA,
            _BLK_PRINTER_METADATA,
            _BLK_THUMBNAIL,
            _BLK_PRINT_METADATA,
        ]


# ---------------------------------------------------------------------------
# _find_thumbnail_insert_pos
# ---------------------------------------------------------------------------


class TestFindThumbnailInsertPos:
    def _blk(self, btype: int) -> bytes:
        return struct.pack("<HHI", btype, 0, 4) + b"data" + b"\x00" * 4

    def test_empty_list(self):
        assert _find_thumbnail_insert_pos([]) == 0

    def test_after_file_and_printer_meta(self):
        blocks = [self._blk(0), self._blk(3), self._blk(4), self._blk(2)]
        assert _find_thumbnail_insert_pos(blocks) == 2

    def test_only_print_meta(self):
        blocks = [self._blk(4)]
        assert _find_thumbnail_insert_pos(blocks) == 0

    def test_only_file_meta(self):
        blocks = [self._blk(0)]
        assert _find_thumbnail_insert_pos(blocks) == 1


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
        # After round-trip, verify raw params bytes match bgcode spec
        # order (format, width, height).  gcode_lib's .width/.height
        # properties interpret these in a different order, so we check
        # the raw params directly.
        fmt0, w0, h0 = struct.unpack_from("<HHH", gf2.thumbnails[0].params)
        assert (fmt0, w0, h0) == (_IMG_PNG, 16, 16)
        fmt1, w1, h1 = struct.unpack_from("<HHH", gf2.thumbnails[1].params)
        assert (fmt1, w1, h1) == (_IMG_PNG, 220, 124)
        assert gf2.thumbnails[0].data == png16
        assert gf2.thumbnails[1].data == png220


# ---------------------------------------------------------------------------
# Helpers for slicer metadata tests
# ---------------------------------------------------------------------------


def _build_slicer_meta_block(text: str, *, compressed: bool = False) -> bytes:
    """Build a SLICER_METADATA block from INI-style text."""
    payload = text.encode("utf-8")
    params = struct.pack("<H", 0)  # encoding = raw/utf8
    if compressed:
        comp_payload = zlib.compress(payload)
        hdr = struct.pack("<HHI", _BLK_SLICER_METADATA, _COMP_DEFLATE, len(payload))
        cs = struct.pack("<I", len(comp_payload))
        body = hdr + cs + params + comp_payload
    else:
        hdr = struct.pack("<HHI", _BLK_SLICER_METADATA, _COMP_NONE, len(payload))
        body = hdr + params + payload
    crc = struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
    return body + crc


def _build_meta_block(btype: int, text: str = "data") -> bytes:
    """Build a simple uncompressed metadata block of the given type."""
    payload = text.encode("utf-8")
    params = struct.pack("<H", 0)
    hdr = struct.pack("<HHI", btype, _COMP_NONE, len(payload))
    body = hdr + params + payload
    crc = struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
    return body + crc


# ---------------------------------------------------------------------------
# _find_slicer_meta_index
# ---------------------------------------------------------------------------


class TestFindSlicerMetaIndex:
    def test_finds_slicer_meta(self):
        blocks = [
            _build_meta_block(_BLK_FILE_METADATA),
            _build_meta_block(_BLK_PRINTER_METADATA),
            _build_slicer_meta_block("key=val"),
        ]
        assert _find_slicer_meta_index(blocks) == 2

    def test_no_slicer_meta(self):
        blocks = [
            _build_meta_block(_BLK_FILE_METADATA),
            _build_meta_block(_BLK_PRINTER_METADATA),
        ]
        assert _find_slicer_meta_index(blocks) is None

    def test_empty_blocks(self):
        assert _find_slicer_meta_index([]) is None


# ---------------------------------------------------------------------------
# _rebuild_slicer_meta_block
# ---------------------------------------------------------------------------


class TestRebuildSlicerMetaBlock:
    def test_update_existing_key(self):
        block = _build_slicer_meta_block("printer_settings_id=\nother=123\n")
        new_block = _rebuild_slicer_meta_block(
            block, {"printer_settings_id": "Prusa CORE One HF0.4 nozzle"}
        )
        # Decode the new payload.
        _, comp, usize = struct.unpack_from("<HHI", new_block, 0)
        assert comp == _COMP_NONE
        text = new_block[10 : 10 + usize].decode("utf-8")
        assert "printer_settings_id=Prusa CORE One HF0.4 nozzle" in text
        assert "other=123" in text

    def test_add_missing_key(self):
        block = _build_slicer_meta_block("existing=value\n")
        new_block = _rebuild_slicer_meta_block(
            block, {"printer_settings_id": "Test Printer"}
        )
        _, _, usize = struct.unpack_from("<HHI", new_block, 0)
        text = new_block[10 : 10 + usize].decode("utf-8")
        assert "printer_settings_id=Test Printer" in text
        assert "existing=value" in text

    def test_does_not_match_substring_key(self):
        block = _build_slicer_meta_block(
            "physical_printer_settings_id=orig\nprinter_settings_id=\n"
        )
        new_block = _rebuild_slicer_meta_block(
            block, {"printer_settings_id": "Patched"}
        )
        _, _, usize = struct.unpack_from("<HHI", new_block, 0)
        text = new_block[10 : 10 + usize].decode("utf-8")
        assert "physical_printer_settings_id=orig" in text
        assert "printer_settings_id=Patched" in text

    def test_deflate_compressed_block(self):
        block = _build_slicer_meta_block(
            "printer_settings_id=\n", compressed=True
        )
        new_block = _rebuild_slicer_meta_block(
            block, {"printer_settings_id": "Compressed Printer"}
        )
        # Verify it's still deflate.
        _, comp, usize = struct.unpack_from("<HHI", new_block, 0)
        assert comp == _COMP_DEFLATE
        cs = struct.unpack_from("<I", new_block, 8)[0]
        compressed = new_block[14 : 14 + cs]
        text = zlib.decompress(compressed).decode("utf-8")
        assert "printer_settings_id=Compressed Printer" in text

    def test_unknown_compression_returns_unchanged(self):
        # Build a block with comp=2 (heatshrink — unsupported).
        payload = b"printer_settings_id=\n"
        params = struct.pack("<H", 0)
        hdr = struct.pack("<HHI", _BLK_SLICER_METADATA, 2, len(payload))
        body = hdr + params + payload
        crc = struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)
        block = body + crc
        result = _rebuild_slicer_meta_block(block, {"printer_settings_id": "X"})
        assert result == block

    def test_crc_valid_after_rebuild(self):
        block = _build_slicer_meta_block("printer_settings_id=\n")
        new_block = _rebuild_slicer_meta_block(
            block, {"printer_settings_id": "CRC Test"}
        )
        stored_crc = struct.unpack_from("<I", new_block, len(new_block) - 4)[0]
        computed_crc = zlib.crc32(new_block[:-4]) & 0xFFFFFFFF
        assert stored_crc == computed_crc


# ---------------------------------------------------------------------------
# patch_slicer_metadata
# ---------------------------------------------------------------------------


class TestPatchSlicerMetadata:
    def _make_gf(self, source_format="bgcode", slicer_text="printer_settings_id=\n"):
        gf = gl.GCodeFile(
            lines=[],
            thumbnails=[],
            source_format=source_format,
        )
        if source_format == "bgcode":
            gf._bgcode_file_hdr = b"GCDE" + struct.pack("<I", 1) + struct.pack("<H", 1)
            gf._bgcode_nongcode_blocks = [
                _build_meta_block(_BLK_FILE_METADATA),
                _build_meta_block(_BLK_PRINTER_METADATA),
                _build_slicer_meta_block(slicer_text),
            ]
        return gf

    def test_patches_coreone_04(self):
        gf = self._make_gf()
        patch_slicer_metadata(gf, "COREONE", 0.4)
        block = gf._bgcode_nongcode_blocks[2]
        _, _, usize = struct.unpack_from("<HHI", block, 0)
        text = block[10 : 10 + usize].decode("utf-8")
        assert "printer_settings_id=Prusa CORE One HF0.4 nozzle" in text

    def test_patches_coreone_025(self):
        gf = self._make_gf()
        patch_slicer_metadata(gf, "COREONE", 0.25)
        block = gf._bgcode_nongcode_blocks[2]
        _, _, usize = struct.unpack_from("<HHI", block, 0)
        text = block[10 : 10 + usize].decode("utf-8")
        assert "printer_settings_id=Prusa CORE One 0.25 nozzle" in text

    def test_skips_ascii_gcode(self):
        gf = self._make_gf("text")
        patch_slicer_metadata(gf, "COREONE", 0.4)
        # No crash — just returns silently.

    def test_skips_unknown_printer(self, capsys):
        gf = self._make_gf()
        patch_slicer_metadata(gf, "UNKNOWN", 0.4, verbose=True)
        captured = capsys.readouterr()
        assert "No printer_settings_id mapping" in captured.out

    def test_skips_unknown_nozzle(self, capsys):
        gf = self._make_gf()
        patch_slicer_metadata(gf, "COREONE", 0.35, verbose=True)
        captured = capsys.readouterr()
        assert "No printer_settings_id mapping" in captured.out

    def test_skips_empty_blocks(self):
        gf = self._make_gf()
        gf._bgcode_nongcode_blocks = []
        patch_slicer_metadata(gf, "COREONE", 0.4)
        # No crash — just returns.

    def test_skips_no_slicer_meta_block(self):
        gf = self._make_gf()
        gf._bgcode_nongcode_blocks = [
            _build_meta_block(_BLK_FILE_METADATA),
        ]
        patch_slicer_metadata(gf, "COREONE", 0.4)
        # No crash — returns when _find_slicer_meta_index returns None.

    def test_verbose_output(self, capsys):
        gf = self._make_gf()
        patch_slicer_metadata(gf, "COREONE", 0.4, verbose=True)
        captured = capsys.readouterr()
        assert "Patched printer_settings_id=" in captured.out

    def test_failure_warns(self):
        gf = self._make_gf()
        # Corrupt the slicer block: declare deflate compression but provide
        # invalid compressed data to trigger a zlib.error inside _rebuild.
        gf._bgcode_nongcode_blocks[2] = (
            struct.pack("<HHI", _BLK_SLICER_METADATA, _COMP_DEFLATE, 10)
            + struct.pack("<I", 3)          # compressed_size = 3
            + struct.pack("<H", 0)          # params
            + b"\xff\xff\xff"               # invalid compressed data
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            patch_slicer_metadata(gf, "COREONE", 0.4)
            assert len(w) == 1
            assert "Slicer metadata patch failed" in str(w[0].message)

    def test_does_not_corrupt_physical_printer_settings_id(self):
        gf = self._make_gf(
            slicer_text=(
                "physical_printer_settings_id=My Printer\n"
                "printer_settings_id=\n"
            )
        )
        patch_slicer_metadata(gf, "COREONE", 0.6)
        block = gf._bgcode_nongcode_blocks[2]
        _, _, usize = struct.unpack_from("<HHI", block, 0)
        text = block[10 : 10 + usize].decode("utf-8")
        assert "physical_printer_settings_id=My Printer" in text
        assert "printer_settings_id=Prusa CORE One HF0.6 nozzle" in text


# ---------------------------------------------------------------------------
# _needs_subprocess_render
# ---------------------------------------------------------------------------


class TestNeedsSubprocessRender:
    @patch("filament_calibrator.thumbnail.platform")
    def test_true_on_darwin(self, mock_platform):
        mock_platform.system.return_value = "Darwin"
        assert _needs_subprocess_render() is True

    @patch("filament_calibrator.thumbnail.platform")
    def test_false_on_linux(self, mock_platform):
        mock_platform.system.return_value = "Linux"
        assert _needs_subprocess_render() is False


# ---------------------------------------------------------------------------
# _subprocess_render_worker
# ---------------------------------------------------------------------------


class TestSubprocessRenderWorker:
    @patch("filament_calibrator.thumbnail._render_vtk")
    def test_success(self, mock_render):
        mock_render.return_value = b"PNG_DATA"
        queue = MagicMock()
        _subprocess_render_worker(queue, "/tmp/t.stl", 64, 64, 64, 64, False)
        queue.put.assert_called_once_with(("ok", b"PNG_DATA"))

    @patch("filament_calibrator.thumbnail._render_vtk")
    def test_error(self, mock_render):
        mock_render.side_effect = RuntimeError("vtk exploded")
        queue = MagicMock()
        _subprocess_render_worker(queue, "/tmp/t.stl", 64, 64, 64, 64, False)
        queue.put.assert_called_once()
        status, msg = queue.put.call_args[0][0]
        assert status == "error"
        assert "vtk exploded" in msg


# ---------------------------------------------------------------------------
# _render_in_subprocess
# ---------------------------------------------------------------------------


class TestRenderInSubprocess:
    @patch("filament_calibrator.thumbnail.mp")
    def test_success(self, mock_mp_mod):
        ctx = MagicMock()
        mock_mp_mod.get_context.return_value = ctx

        mock_queue = MagicMock()
        mock_queue.get_nowait.return_value = ("ok", b"PNG_BYTES")
        ctx.Queue.return_value = mock_queue

        mock_proc = MagicMock()
        mock_proc.exitcode = 0
        ctx.Process.return_value = mock_proc

        result = _render_in_subprocess("/t.stl", 64, 64, 64, 64, False)
        assert result == b"PNG_BYTES"
        mock_proc.start.assert_called_once()
        mock_proc.join.assert_called_once_with(timeout=120)

    @patch("filament_calibrator.thumbnail.mp")
    def test_nonzero_exit(self, mock_mp_mod):
        ctx = MagicMock()
        mock_mp_mod.get_context.return_value = ctx
        ctx.Queue.return_value = MagicMock()

        mock_proc = MagicMock()
        mock_proc.exitcode = 1
        ctx.Process.return_value = mock_proc

        with pytest.raises(RuntimeError, match="exit code 1"):
            _render_in_subprocess("/t.stl", 64, 64, 64, 64, False)

    @patch("filament_calibrator.thumbnail.mp")
    def test_timeout(self, mock_mp_mod):
        ctx = MagicMock()
        mock_mp_mod.get_context.return_value = ctx
        ctx.Queue.return_value = MagicMock()

        mock_proc = MagicMock()
        mock_proc.exitcode = None  # still running
        ctx.Process.return_value = mock_proc

        with pytest.raises(RuntimeError, match="timed out"):
            _render_in_subprocess("/t.stl", 64, 64, 64, 64, False)
        mock_proc.kill.assert_called_once()

    @patch("filament_calibrator.thumbnail.mp")
    def test_worker_error(self, mock_mp_mod):
        ctx = MagicMock()
        mock_mp_mod.get_context.return_value = ctx

        mock_queue = MagicMock()
        mock_queue.get_nowait.return_value = ("error", "render broke")
        ctx.Queue.return_value = mock_queue

        mock_proc = MagicMock()
        mock_proc.exitcode = 0
        ctx.Process.return_value = mock_proc

        with pytest.raises(RuntimeError, match="render broke"):
            _render_in_subprocess("/t.stl", 64, 64, 64, 64, False)


# ---------------------------------------------------------------------------
# render_stl_to_png — subprocess path
# ---------------------------------------------------------------------------


class TestRenderStlToPngSubprocess:
    @patch("filament_calibrator.thumbnail._render_in_subprocess")
    @patch("filament_calibrator.thumbnail._needs_subprocess_render", return_value=True)
    def test_delegates_to_subprocess(self, _mock_needs, mock_sub, tmp_path):
        stl = _make_stl_file(tmp_path)
        mock_sub.return_value = b"PNG"
        result = render_stl_to_png(stl, 100, 80)
        assert result == b"PNG"
        mock_sub.assert_called_once_with(stl, 100, 80, 100, 80, False)

    @patch("filament_calibrator.thumbnail._render_in_subprocess")
    @patch("filament_calibrator.thumbnail._needs_subprocess_render", return_value=True)
    def test_subprocess_with_supersample(self, _mock_needs, mock_sub, tmp_path):
        stl = _make_stl_file(tmp_path)
        mock_sub.return_value = b"PNG"
        render_stl_to_png(stl, 16, 16)
        mock_sub.assert_called_once_with(
            stl,
            16 * _SUPERSAMPLE_FACTOR,
            16 * _SUPERSAMPLE_FACTOR,
            16,
            16,
            True,
        )

    @patch(
        "filament_calibrator.thumbnail._render_in_subprocess",
        side_effect=RuntimeError("child failed"),
    )
    @patch("filament_calibrator.thumbnail._needs_subprocess_render", return_value=True)
    def test_subprocess_failure_falls_back_to_png(self, _mock_needs, _mock_sub, tmp_path):
        stl = _make_stl_file(tmp_path)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            png = render_stl_to_png(stl, 32, 24)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        img = Image.open(io.BytesIO(png))
        assert img.size == (32, 24)
        assert any("fallback thumbnail" in str(msg.message) for msg in w)
