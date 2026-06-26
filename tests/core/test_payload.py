"""Tests for bellbird.core.payload — build_options and build_api_messages."""

import pytest

from bellbird.core.config import BellbirdConfig
from bellbird.core.conversation import Conversation
from bellbird.core.payload import build_options, build_api_messages


class TestBuildOptions:
    def test_always_includes_base_keys(self):
        cfg = BellbirdConfig()
        opts = build_options(cfg)
        for key in ("temperature", "max_tokens", "top_p", "top_k", "repeat_penalty", "min_p"):
            assert key in opts

    def test_seed_omitted_when_negative(self):
        cfg = BellbirdConfig(seed=-1)
        assert "seed" not in build_options(cfg)

    def test_seed_included_when_zero_or_positive(self):
        for seed_val in (0, 42):
            opts = build_options(BellbirdConfig(seed=seed_val))
            assert opts["seed"] == seed_val

    def test_stop_omitted_when_empty(self):
        assert "stop" not in build_options(BellbirdConfig(stop=[]))

    def test_stop_included_when_non_empty(self):
        cfg = BellbirdConfig(stop=["</s>", "<|end|>"])
        opts = build_options(cfg)
        assert opts["stop"] == ["</s>", "<|end|>"]

    def test_stop_is_copy_not_same_reference(self):
        stop_list = ["</s>"]
        cfg = BellbirdConfig(stop=stop_list)
        opts = build_options(cfg)
        opts["stop"].append("extra")  # type: ignore[union-attr]
        assert cfg.stop == ["</s>"]  # original unchanged

    def test_values_match_config(self):
        cfg = BellbirdConfig(temperature=0.5, max_tokens=2048, top_p=0.85,
                              top_k=20, repeat_penalty=1.2, min_p=0.1)
        opts = build_options(cfg)
        assert opts["temperature"] == 0.5
        assert opts["max_tokens"] == 2048
        assert opts["min_p"] == 0.1


class TestBuildApiMessages:
    def test_empty_system_prompt_not_included(self):
        cfg = BellbirdConfig(system_prompt="")
        conv = Conversation()
        msgs = build_api_messages(cfg, conv)
        assert msgs == []

    def test_whitespace_only_system_prompt_not_included(self):
        cfg = BellbirdConfig(system_prompt="   ")
        conv = Conversation()
        msgs = build_api_messages(cfg, conv)
        assert msgs == []

    def test_non_empty_system_prompt_is_first(self):
        cfg = BellbirdConfig(system_prompt="Eres un asistente.")
        conv = Conversation()
        msgs = build_api_messages(cfg, conv)
        assert msgs[0] == {"role": "system", "content": "Eres un asistente."}

    def test_conversation_messages_follow_system(self):
        cfg = BellbirdConfig(system_prompt="System.")
        conv = Conversation()
        conv.add_message("user", "Hola")
        conv.add_message("assistant", "Hola!")
        msgs = build_api_messages(cfg, conv)
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_no_system_prompt_returns_only_history(self):
        cfg = BellbirdConfig(system_prompt="")
        conv = Conversation()
        conv.add_message("user", "Hola")
        msgs = build_api_messages(cfg, conv)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_returns_new_list_each_call(self):
        cfg = BellbirdConfig(system_prompt="S.")
        conv = Conversation()
        a = build_api_messages(cfg, conv)
        b = build_api_messages(cfg, conv)
        assert a is not b
