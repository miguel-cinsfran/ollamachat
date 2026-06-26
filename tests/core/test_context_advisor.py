"""Tests for bellbird.core.context_advisor — strict TDD, wx-free.

Covers read_vram, FitReport, estimate_fit, token_count, PreSendSnapshot,
PreSendVerdict, and pre_send_check.
"""

import sys
from unittest.mock import MagicMock, patch, call

import pytest
import requests


# ─── ReadVram (T-WU1-03) — 6 cases ────────────────────────────────────────────


class TestReadVram:
    """Tests for read_vram."""

    def test_non_win32_returns_none_none(self):
        """GIVEN sys.platform != 'win32'
        WHEN read_vram() runs
        THEN returns (None, None) and subprocess.run is NOT called."""
        from bellbird.core.context_advisor import read_vram

        with patch("bellbird.core.context_advisor.sys.platform", "linux"):
            with patch("bellbird.core.context_advisor.subprocess.run") as mock_run:
                result = read_vram()
        assert result == (None, None)
        mock_run.assert_not_called()

    def test_win32_happy_path(self):
        """GIVEN sys.platform == 'win32' and nvidia-smi returns valid CSV
        WHEN read_vram() runs
        THEN returns (free_mb, total_mb) as ints."""
        from bellbird.core.context_advisor import read_vram

        mock_proc = MagicMock()
        # nvidia-smi --query-gpu=memory.total,memory.free returns "total, free"
        mock_proc.stdout = "8192, 12288\n"  # total=8192 MB, free=12288 MB
        mock_proc.returncode = 0

        with patch("bellbird.core.context_advisor.sys.platform", "win32"):
            with patch(
                "bellbird.core.context_advisor.subprocess.run",
                return_value=mock_proc,
            ) as mock_run:
                result = read_vram()

        # Returns (free_mb, total_mb)
        assert result == (12288, 8192)
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert "--query-gpu=memory.total,memory.free" in kwargs.get("args", args[0])

    def test_win32_timeout_returns_none_none(self):
        """GIVEN subprocess raises TimeoutExpired
        WHEN read_vram() runs
        THEN returns (None, None)."""
        from bellbird.core.context_advisor import read_vram
        import subprocess

        with patch("bellbird.core.context_advisor.sys.platform", "win32"):
            with patch(
                "bellbird.core.context_advisor.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=1),
            ):
                result = read_vram()
        assert result == (None, None)

    def test_win32_filenotfound_returns_none_none(self):
        """GIVEN nvidia-smi not found
        WHEN read_vram() runs
        THEN returns (None, None)."""
        from bellbird.core.context_advisor import read_vram

        with patch("bellbird.core.context_advisor.sys.platform", "win32"):
            with patch(
                "bellbird.core.context_advisor.subprocess.run",
                side_effect=FileNotFoundError("nvidia-smi not found"),
            ):
                result = read_vram()
        assert result == (None, None)

    def test_win32_nonzero_exit_returns_none_none(self):
        """GIVEN nvidia-smi returns non-zero exit code
        WHEN read_vram() runs
        THEN returns (None, None)."""
        from bellbird.core.context_advisor import read_vram

        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.returncode = 1

        with patch("bellbird.core.context_advisor.sys.platform", "win32"):
            with patch(
                "bellbird.core.context_advisor.subprocess.run",
                return_value=mock_proc,
            ):
                result = read_vram()
        assert result == (None, None)

    def test_win32_malformed_output_returns_none_none(self):
        """GIVEN nvidia-smi returns malformed CSV
        WHEN read_vram() runs
        THEN returns (None, None)."""
        from bellbird.core.context_advisor import read_vram

        mock_proc = MagicMock()
        mock_proc.stdout = "not, numbers\n"
        mock_proc.returncode = 0

        with patch("bellbird.core.context_advisor.sys.platform", "win32"):
            with patch(
                "bellbird.core.context_advisor.subprocess.run",
                return_value=mock_proc,
            ):
                result = read_vram()
        assert result == (None, None)


# ─── FitReport + estimate_fit (T-WU1-04) — 5 cases ────────────────────────────


class TestFitReport:
    """Tests for FitReport frozen dataclass."""

    def test_frozen_mutation_raises(self):
        """GIVEN a FitReport instance
        WHEN a field is mutated
        THEN dataclasses.FrozenInstanceError is raised."""
        from bellbird.core.context_advisor import FitReport
        import dataclasses

        report = FitReport(status="fits", reason_es="Cabe", confidence="high")
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.status = "spills"


class TestEstimateFit:
    """Tests for estimate_fit."""

    def test_fits_with_high_confidence(self):
        """GIVEN small model + small ctx + plenty VRAM
        WHEN estimate_fit runs
        THEN fits=True, confidence=high."""
        from bellbird.core.context_advisor import estimate_fit
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata(
            block_count=32, context_length=4096,
            file_type="Q4_K_M", size_bytes=2_000_000_000,
        )
        report = estimate_fit(meta, ctx_size=4096, vram_free_mb=8192)

        assert report.status == "fits"
        assert report.confidence == "high"
        assert "VRAM libre" in report.reason_es
        assert "cabe" in report.reason_es

    def test_spills_with_conservative_warning(self):
        """GIVEN large model + large ctx + limited VRAM
        WHEN estimate_fit runs
        THEN spills_to_ram and message warns."""
        from bellbird.core.context_advisor import estimate_fit
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata(
            block_count=32, context_length=32768,
            file_type="Q4_K_M", size_bytes=4_000_000_000,
        )
        report = estimate_fit(meta, ctx_size=32768, vram_free_mb=4096)

        assert report.status == "spills"
        assert "podría desbordar" in report.reason_es

    def test_unknown_when_vram_none(self):
        """GIVEN vram_free_mb is None
        WHEN estimate_fit runs
        THEN unknown=True and message starts with 'VRAM desconocida'."""
        from bellbird.core.context_advisor import estimate_fit
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata(
            block_count=32, context_length=4096,
            file_type="Q4_K_M", size_bytes=2_000_000_000,
        )
        report = estimate_fit(meta, ctx_size=4096, vram_free_mb=None)

        assert report.status == "unknown"
        assert "VRAM desconocida" in report.reason_es

    def test_unknown_when_size_bytes_none(self):
        """GIVEN size_bytes is None
        WHEN estimate_fit runs
        THEN unknown=True."""
        from bellbird.core.context_advisor import estimate_fit
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata(
            block_count=32, context_length=4096,
            file_type="Q4_K_M", size_bytes=None,
        )
        report = estimate_fit(meta, ctx_size=4096, vram_free_mb=8192)

        assert report.status == "unknown"

    def test_reason_es_is_spanish_one_liner(self):
        """GIVEN a fit scenario
        WHEN estimate_fit runs
        THEN reason_es is a Spanish string with relevant info."""
        from bellbird.core.context_advisor import estimate_fit
        from bellbird.core.model_meta import GGUFMetadata

        meta = GGUFMetadata(
            block_count=32, context_length=4096,
            file_type="Q4_K_M", size_bytes=3_000_000_000,
        )
        report = estimate_fit(meta, ctx_size=8192, vram_free_mb=6144)

        assert isinstance(report.reason_es, str)
        assert len(report.reason_es) > 0
        # Must contain VRAM reference
        assert any(w in report.reason_es for w in ("VRAM", "GB", "MB"))


# ─── token_count (T-WU1-05) — 5 cases ─────────────────────────────────────────


class TestTokenCount:
    """Tests for token_count."""

    def test_happy_path(self):
        """GIVEN POST /tokenize returns 200 with tokens array
        WHEN token_count runs
        THEN returns len(tokens)."""
        from bellbird.core.context_advisor import token_count

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tokens": [1, 2, 3, 4, 5]}
        mock_session.post.return_value = mock_response

        result = token_count(
            text="hi", base_url="http://localhost:8080",
            session=mock_session,
        )
        assert result == 5
        mock_session.post.assert_called_once()
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"]["content"] == "hi"
        assert kwargs["json"]["add_special"] is False

    def test_connection_error_returns_none(self):
        """GIVEN POST raises ConnectionError
        WHEN token_count runs
        THEN returns None."""
        from bellbird.core.context_advisor import token_count

        mock_session = MagicMock()
        mock_session.post.side_effect = requests.ConnectionError("refused")

        result = token_count(
            text="hi", base_url="http://localhost:8080",
            session=mock_session,
        )
        assert result is None

    def test_4xx_error_returns_none(self):
        """GIVEN POST returns 400
        WHEN token_count runs
        THEN returns None."""
        from bellbird.core.context_advisor import token_count

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_session.post.return_value = mock_response

        result = token_count(
            text="hi", base_url="http://localhost:8080",
            session=mock_session,
        )
        assert result is None

    def test_5xx_error_returns_none(self):
        """GIVEN POST returns 500
        WHEN token_count runs
        THEN returns None."""
        from bellbird.core.context_advisor import token_count

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_session.post.return_value = mock_response

        result = token_count(
            text="hi", base_url="http://localhost:8080",
            session=mock_session,
        )
        assert result is None

    def test_malformed_json_returns_none(self):
        """GIVEN POST returns non-JSON body
        WHEN token_count runs
        THEN returns None."""
        from bellbird.core.context_advisor import token_count

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_session.post.return_value = mock_response

        result = token_count(
            text="hi", base_url="http://localhost:8080",
            session=mock_session,
        )
        assert result is None


# ─── PreSendSnapshot + PreSendVerdict + pre_send_check (T-WU1-06) — 7 cases ──


class TestPreSendDataclasses:
    """Tests for PreSendSnapshot and PreSendVerdict frozen dataclasses."""

    def test_snapshot_frozen(self):
        """GIVEN a PreSendSnapshot instance
        WHEN a field is mutated
        THEN dataclasses.FrozenInstanceError is raised."""
        from bellbird.core.context_advisor import PreSendSnapshot
        import dataclasses

        snap = PreSendSnapshot(
            estimated_tokens=100, n_ctx=4096,
            safe_mode=False, warn_once=False,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            snap.estimated_tokens = 200

    def test_verdict_frozen(self):
        """GIVEN a PreSendVerdict instance
        WHEN a field is mutated
        THEN dataclasses.FrozenInstanceError is raised."""
        from bellbird.core.context_advisor import PreSendVerdict
        import dataclasses

        v = PreSendVerdict(decision="allow", reason_es=None)
        with pytest.raises(dataclasses.FrozenInstanceError):
            v.decision = "block"


class TestPreSendCheck:
    """Tests for pre_send_check."""

    def test_allow_when_fits(self):
        """GIVEN safe_mode ON + estimated_tokens < n_ctx
        WHEN pre_send_check runs
        THEN decision is allow."""
        from bellbird.core.context_advisor import (
            pre_send_check, PreSendSnapshot,
        )

        snap = PreSendSnapshot(
            estimated_tokens=100, n_ctx=4096,
            safe_mode=True, warn_once=False,
        )
        verdict = pre_send_check(snap)
        assert verdict.decision == "allow"
        assert verdict.reason_es == ""

    def test_allow_when_fits_and_safe_off(self):
        """GIVEN safe_mode OFF + estimated_tokens < n_ctx
        WHEN pre_send_check runs
        THEN decision is allow."""
        from bellbird.core.context_advisor import (
            pre_send_check, PreSendSnapshot,
        )

        snap = PreSendSnapshot(
            estimated_tokens=100, n_ctx=4096,
            safe_mode=False, warn_once=False,
        )
        verdict = pre_send_check(snap)
        assert verdict.decision == "allow"
        assert verdict.reason_es == ""

    def test_warn_when_overflows_and_safe_off(self):
        """GIVEN safe_mode OFF + estimated_tokens > n_ctx
        WHEN pre_send_check runs
        THEN decision is warn with Spanish reason."""
        from bellbird.core.context_advisor import (
            pre_send_check, PreSendSnapshot,
        )

        snap = PreSendSnapshot(
            estimated_tokens=5000, n_ctx=4096,
            safe_mode=False, warn_once=False,
        )
        verdict = pre_send_check(snap)
        assert verdict.decision == "warn"
        assert verdict.reason_es is not None
        assert len(verdict.reason_es) > 0

    def test_block_when_overflows_and_safe_on(self):
        """GIVEN safe_mode ON + estimated_tokens > n_ctx
        WHEN pre_send_check runs
        THEN decision is block with Spanish reason."""
        from bellbird.core.context_advisor import (
            pre_send_check, PreSendSnapshot,
        )

        snap = PreSendSnapshot(
            estimated_tokens=5000, n_ctx=4096,
            safe_mode=True, warn_once=False,
        )
        verdict = pre_send_check(snap)
        assert verdict.decision == "block"
        assert verdict.reason_es is not None
        assert len(verdict.reason_es) > 0

    def test_allow_when_n_ctx_none(self):
        """GIVEN n_ctx is None (server not probed)
        WHEN pre_send_check runs
        THEN decision is allow (defer to server)."""
        from bellbird.core.context_advisor import (
            pre_send_check, PreSendSnapshot,
        )

        snap = PreSendSnapshot(
            estimated_tokens=5000, n_ctx=None,
            safe_mode=True, warn_once=False,
        )
        verdict = pre_send_check(snap)
        assert verdict.decision == "allow"
        assert verdict.reason_es == ""

    def test_overflow_block_with_vram_gate(self):
        """GIVEN model_size_bytes > vram_free_mb * 1024 * 1024
        AND n_ctx is None
        WHEN pre_send_check runs
        THEN decision is block (VRAM overflow with safe_mode ON)."""
        from bellbird.core.context_advisor import (
            pre_send_check, PreSendSnapshot,
        )

        snap = PreSendSnapshot(
            estimated_tokens=0, n_ctx=None,
            safe_mode=True, warn_once=False,
            vram_free_mb=2048,
            model_size_bytes=4_000_000_000,
        )
        verdict = pre_send_check(snap)
        assert verdict.decision == "block"
