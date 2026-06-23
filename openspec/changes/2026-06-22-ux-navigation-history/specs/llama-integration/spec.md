# llama-integration Spec — Delta for v0.3.0

## Purpose

Adds an optional `on_usage` callback to `LlamaClient.chat_stream` so the UI can capture and display token-usage statistics reported by `llama-server` in the final SSE chunk. Existing streaming, abort, and threading contracts are preserved unchanged.

## MODIFIED Requirements

### REQ-LLAMA-003: Stream chat completions

(Previously: `chat_stream(messages, options, on_token, on_done, on_error)`.)

`LlamaClient.chat_stream(messages, options, on_token, on_done, on_error, on_usage: Callable[[dict], None] | None = None)` MUST add an optional `on_usage` keyword parameter defaulting to `None`. Inside `_stream_worker`, when an SSE chunk's decoded JSON contains an `"usage"` key, the worker MUST call `wx.CallAfter(on_usage, chunk["usage"])` IF `on_usage is not None`. The absence of a `"usage"` key in any chunk MUST be silent (no error, no callback). The original `on_token` / `on_done` / `on_error` contract, the daemon thread, the SSE parser, the abort event, and the body shape are unchanged.

#### Scenario: usage chunk triggers callback

- **GIVEN** a stubbed stream whose final SSE event is `{"usage": {"prompt_tokens": 12, "completion_tokens": 80, "total_tokens": 92}}`
- **AND** `on_usage` is a fake recording function
- **WHEN** `chat_stream(..., on_usage=on_usage)` is called
- **THEN** `on_usage` is invoked exactly once
- **AND** the argument is the dict `{"prompt_tokens": 12, "completion_tokens": 80, "total_tokens": 92}`
- **AND** the invocation is wrapped in `wx.CallAfter`

#### Scenario: missing usage is silent

- **GIVEN** a stream that yields no `"usage"` key in any chunk
- **AND** `on_usage` is `None`
- **WHEN** `chat_stream(...)` is called
- **THEN** no exception is raised
- **AND** `on_token` and `on_done` are invoked as before

#### Scenario: callback is called via CallAfter

- **GIVEN** `on_usage` is a fake function
- **WHEN** the worker detects a `"usage"` key
- **THEN** the recorded call shape is `wx.CallAfter(on_usage, usage_dict)`
- **AND** `on_usage` itself is NOT invoked synchronously from the worker thread

#### Scenario: backward compat — on_usage defaults to None

- **GIVEN** `chat_stream(messages, options, on_token, on_done, on_error)` is called WITHOUT `on_usage`
- **WHEN** the stream yields a usage chunk
- **THEN** no `TypeError` is raised
- **AND** the stream completes normally
