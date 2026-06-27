"""Tests for bellbird.core.model_meta — strict TDD, wx-free.

Covers find_mmproj_for_model with temporary directories:
no-sibling, single per pattern, multi → None, alphabetical tie-break,
edge cases (no parent dir, missing model path).
"""

from pathlib import Path

import pytest


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestFindMmprojForModel:
    """Tests for find_mmproj_for_model."""

    def test_no_siblings_returns_none(self, tmp_path: Path) -> None:
        """Given a dir with only the model file, returns None."""
        model = tmp_path / "Llama-3.2-11B.gguf"
        model.write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result is None

    def test_pattern1_single_match(self, tmp_path: Path) -> None:
        """Given a dir with mmproj-Llama*.gguf, returns it."""
        model = tmp_path / "Llama-3.2-11B.gguf"
        model.write_text("")
        proj = tmp_path / "mmproj-Llama-3.2-11B-f16.gguf"
        proj.write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result == proj.resolve()

    def test_pattern1_multi_match_returns_none(self, tmp_path: Path) -> None:
        """Given multiple mmproj-*.gguf, refuses and returns None."""
        model = tmp_path / "model.gguf"
        model.write_text("")
        (tmp_path / "mmproj-A.gguf").write_text("")
        (tmp_path / "mmproj-B.gguf").write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result is None

    def test_pattern2_fallback(self, tmp_path: Path) -> None:
        """Given no mmproj- prefix but *mmproj* match, returns it."""
        model = tmp_path / "model.gguf"
        model.write_text("")
        proj = tmp_path / "llama-vision-mmproj-v1.gguf"
        proj.write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result == proj.resolve()

    def test_pattern3_lowest(self, tmp_path: Path) -> None:
        """Given no pattern 1/2 match but *.mmproj.gguf, returns it."""
        model = tmp_path / "model.gguf"
        model.write_text("")
        proj = tmp_path / "vision.mmproj.gguf"
        proj.write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result == proj.resolve()

    def test_pattern2_multi_match_returns_none(self, tmp_path: Path) -> None:
        """Pattern 2 with multiple *mmproj* matches refuses and returns None.

        This protects non-vision models in shared directories (e.g. ~/models/)
        where multiple named mmproj files coexist — none of which belongs to
        the model being loaded.
        """
        model = tmp_path / "model.gguf"
        model.write_text("")
        (tmp_path / "a-mmproj-v1.gguf").write_text("")
        (tmp_path / "b-mmproj-v2.gguf").write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result is None

    def test_pattern0_prefix_match_single(self, tmp_path: Path) -> None:
        """Pattern 0: mmproj named with model prefix is auto-detected.

        This covers co-located mmproj files like
        ``GLM-4.6V-Flash-mmproj-F16.gguf`` next to ``GLM-4.6V-Flash-Q4_K_M.gguf``
        in a shared models directory.
        """
        model = tmp_path / "GLM-4.6V-Flash-Q4_K_M.gguf"
        model.write_text("")
        glm_proj = tmp_path / "GLM-4.6V-Flash-mmproj-F16.gguf"
        glm_proj.write_text("")
        # Unrelated mmproj for another model — must NOT be picked
        (tmp_path / "gemma-4-12B-it-qat-mmproj-F16.gguf").write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result == glm_proj.resolve()

    def test_pattern0_prefix_match_disambiguates(self, tmp_path: Path) -> None:
        """Pattern 0 picks the right projector when multiple named mmproj co-exist."""
        gemma_model = tmp_path / "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf"
        gemma_model.write_text("")
        (tmp_path / "GLM-4.6V-Flash-mmproj-F16.gguf").write_text("")
        gemma_proj = tmp_path / "gemma-4-12B-it-qat-mmproj-F16.gguf"
        gemma_proj.write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(gemma_model)

        assert result == gemma_proj.resolve()

    def test_non_gguf_siblings_ignored(self, tmp_path: Path) -> None:
        """Given non-GGUF siblings, they are not considered."""
        model = tmp_path / "model.gguf"
        model.write_text("")
        (tmp_path / "readme.txt").write_text("")
        (tmp_path / "mmproj-model.gguf").write_text("")
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(model)

        assert result is not None
        assert result.name == "mmproj-model.gguf"

    def test_model_no_parent_dir_returns_none(self) -> None:
        """Given model_path with no parent (e.g. bare filename), returns None."""
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(Path("bare_model.gguf"))

        assert result is None

    def test_model_nonexistent_returns_none(self, tmp_path: Path) -> None:
        """Given model_path that doesn't exist, returns None."""
        from bellbird.core.model_meta import find_mmproj_for_model

        result = find_mmproj_for_model(tmp_path / "nonexistent.gguf")

        assert result is None


# ─── GGUFMetadata (v0.9.0) ─────────────────────────────────────────────────


class TestGGUFMetadata:
    """Tests for GGUFMetadata frozen dataclass."""

    def test_frozen_mutation_raises(self) -> None:
        """GIVEN a GGUFMetadata instance
        WHEN a field is mutated
        THEN dataclasses.FrozenInstanceError is raised."""
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata(
            block_count=32, context_length=4096,
            file_type="Q4_K_M", size_bytes=4_000_000_000,
        )
        import dataclasses
        with pytest.raises(dataclasses.FrozenInstanceError):
            meta.block_count = 64

    def test_all_fields_accessible(self) -> None:
        """GIVEN a GGUFMetadata instance
        THEN all four fields are readable."""
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata(
            block_count=32, context_length=4096,
            file_type="Q4_K_M", size_bytes=4_000_000_000,
        )
        assert meta.block_count == 32
        assert meta.context_length == 4096
        assert meta.file_type == "Q4_K_M"
        assert meta.size_bytes == 4_000_000_000

    def test_all_none_defaults(self) -> None:
        """GIVEN GGUFMetadata with all None fields
        THEN the instance is constructible."""
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata()
        assert meta.block_count is None
        assert meta.context_length is None
        assert meta.file_type is None
        assert meta.size_bytes is None


class TestReadGgufMetadata:
    """Tests for read_gguf_metadata."""

    def test_happy_path_with_synthetic_gguf(self, tmp_path) -> None:
        """GIVEN a minimal valid .gguf with known metadata
        WHEN read_gguf_metadata is called
        THEN a GGUFMetadata is returned with correct fields."""
        import struct
        GGUF_MAGIC = 0x46554747
        VERSION = 3
        GGUF_VALUE_TYPE_UINT32 = 4
        GGUF_VALUE_TYPE_STRING = 8

        def enc_str(s: str) -> bytes:
            data = s.encode("utf-8")
            return struct.pack("<Q", len(data)) + data

        path = tmp_path / "test.gguf"
        with open(path, "wb") as f:
            f.write(struct.pack("<I", GGUF_MAGIC))
            f.write(struct.pack("<I", VERSION))
            f.write(struct.pack("<Q", 0))  # tensor_count
            f.write(struct.pack("<Q", 4))  # kv_count
            # KV: architecture
            f.write(enc_str("general.architecture"))
            f.write(struct.pack("<I", GGUF_VALUE_TYPE_STRING))
            f.write(enc_str("llama"))
            # KV: block_count
            f.write(enc_str("llama.block_count"))
            f.write(struct.pack("<I", GGUF_VALUE_TYPE_UINT32))
            f.write(struct.pack("<I", 32))
            # KV: context_length
            f.write(enc_str("llama.context_length"))
            f.write(struct.pack("<I", GGUF_VALUE_TYPE_UINT32))
            f.write(struct.pack("<I", 4096))
            # KV: file_type
            f.write(enc_str("general.file_type"))
            f.write(struct.pack("<I", GGUF_VALUE_TYPE_UINT32))
            f.write(struct.pack("<I", 15))  # Q4_K_M

        from bellbird.core.model_meta import read_gguf_metadata

        result = read_gguf_metadata(path)
        assert result is not None
        assert result.block_count == 32
        assert result.context_length == 4096
        assert result.file_type == "MOSTLY_Q4_K_M"
        assert result.size_bytes == path.stat().st_size

    def test_nonexistent_file_returns_none(self, tmp_path) -> None:
        """GIVEN a non-existent path
        WHEN read_gguf_metadata is called
        THEN None is returned."""
        from bellbird.core.model_meta import read_gguf_metadata

        result = read_gguf_metadata(tmp_path / "nope.gguf")
        assert result is None

    def test_corrupt_file_returns_none(self, tmp_path) -> None:
        """GIVEN a 0-byte file
        WHEN read_gguf_metadata is called
        THEN None is returned."""
        path = tmp_path / "corrupt.gguf"
        path.write_text("")
        from bellbird.core.model_meta import read_gguf_metadata

        result = read_gguf_metadata(path)
        assert result is None

    def test_import_error_fallback(self, monkeypatch, tmp_path) -> None:
        """GIVEN gguf module import raises ImportError
        WHEN read_gguf_metadata is called
        THEN None is returned without crashing."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "gguf":
                raise ImportError("No module named 'gguf'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        from bellbird.core.model_meta import read_gguf_metadata

        result = read_gguf_metadata(tmp_path / "whatever.gguf")
        assert result is None

    def test_ast_no_top_level_gguf_import(self) -> None:
        """GIVEN core/model_meta.py
        WHEN the source is inspected
        THEN there is NO top-level 'import gguf' (only line-local)."""
        import pathlib
        src = (
            pathlib.Path(__file__).resolve().parent.parent.parent
            / "bellbird/core/model_meta.py"
        ).read_text(encoding="utf-8")
        # Check that "import gguf" only appears inside function bodies,
        # not at module level. Module-level import would be at column 0
        # without indentation.
        import re
        lines = src.split("\n")
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == "import gguf" and not line.startswith((" ", "\t")):
                pytest.fail(
                    f"Line {lineno}: top-level 'import gguf' found in model_meta.py."
                    f" All gguf imports must be line-local (indented inside a function)."
                )


class TestEstimateSizeBytes:
    """Tests for estimate_size_bytes."""

    def test_existing_file_returns_size(self, tmp_path) -> None:
        """GIVEN a 1024-byte file
        WHEN estimate_size_bytes is called
        THEN the result is 1024."""
        path = tmp_path / "model.gguf"
        path.write_bytes(b"x" * 1024)
        from bellbird.core.model_meta import estimate_size_bytes

        result = estimate_size_bytes(path)
        assert result == 1024

    def test_nonexistent_file_returns_none(self, tmp_path) -> None:
        """GIVEN a non-existent path
        WHEN estimate_size_bytes is called
        THEN None is returned."""
        from bellbird.core.model_meta import estimate_size_bytes

        result = estimate_size_bytes(tmp_path / "nope.gguf")
        assert result is None
