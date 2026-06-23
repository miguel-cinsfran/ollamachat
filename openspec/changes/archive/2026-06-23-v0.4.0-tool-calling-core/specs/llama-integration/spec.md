# llama-integration Spec — Delta for v0.4.0

## Purpose

Extends `LlamaClient.chat_stream` with optional tool-calling support: `tools` (the OpenAI-format tool catalog forwarded to llama-server) and `on_tool_call` (a callback fired when the model emits a `tool_calls` delta). Both default to `None`, preserving every v0.3.0 contract (`on_token` / `on_done` / `on_error` / `on_usage`, daemon thread, SSE parser, abort event, body shape, and `wx` import-inside-worker pattern). The buffer-accumulation rule for split SSE fragments and the three new behaviors are in the ADDED Requirements below.

## MODIFIED Requirements

### Requirement: Stream chat completions

(Previously: `chat_stream(messages, options, on_token, on_done, on_error, on_usage=None)`.)

`LlamaClient.chat_stream(messages, options, on_token, on_done, on_error, on_usage=None, on_tool_call: Callable[[str, str, dict], None] | None = None, tools: list[dict] | None = None)` MUST add two optional keyword parameters defaulting to `None`. Both are forwarded to the daemon `threading.Thread` via `args=...` and received by `_stream_worker`.

When `on_tool_call is None` and `tools is None`, behavior is identical to v0.3.0: no `tools` or `tool_choice` keys in the body, no `tool_calls` buffering, no `on_tool_call` dispatch. SSE parser, abort event, threading contract, and the four existing callbacks are unchanged. Full contract for the new parameters is in the three ADDED Requirements below.

#### Scenario: backward compat — both new params default to None

- **GIVEN** `chat_stream(messages, options, on_token, on_done, on_error)` is called WITHOUT `on_tool_call` or `tools`
- **AND** a stream whose final chunk has a `"usage"` key
- **WHEN** the stream completes
- **THEN** no `TypeError` is raised
- **AND** the request body does NOT contain a `tools` or `tool_choice` key
- **AND** `on_usage` is invoked exactly once via `wx.CallAfter` (v0.3.0 behavior preserved)

## ADDED Requirements

### Requirement: chat_stream accepts an on_tool_call callback

`chat_stream` SHALL accept an optional `on_tool_call: Callable[[str, str, dict], None] | None = None` parameter. When the SSE stream reaches a chunk whose `choices[0].finish_reason == "tool_calls"` AND `on_tool_call is not None`, the worker MUST invoke `wx.CallAfter(on_tool_call, tool_name, tool_call_id, arguments_dict)` once per accumulated tool_call, then clear the buffer.

Callback signature: `(tool_name: str, tool_call_id: str, arguments: dict)`. Dispatch uses `wx.CallAfter` (not a direct call) so the callback runs on the wx main thread, mirroring the `on_token` / `on_usage` contract.

#### Scenario: callback fires with parsed args on finish_reason=tool_calls

- **GIVEN** a stubbed stream whose final chunk is `{"choices": [{"finish_reason": "tool_calls", "delta": {"tool_calls": [{"index": 0, "id": "call_abc", "function": {"name": "shell_execute", "arguments": "{\"command\":\"ls\"}"}}]}}]}`
- **AND** `on_tool_call` is a fake recording function
- **WHEN** `chat_stream(..., on_tool_call=on_tool_call)` is called
- **THEN** `on_tool_call` is invoked exactly once
- **AND** the recorded call shape is `wx.CallAfter(on_tool_call, "shell_execute", "call_abc", {"command": "ls"})`

#### Scenario: no callback when finish_reason is never tool_calls

- **GIVEN** a stream whose chunks all have `finish_reason` of `None` or `"stop"`
- **AND** `on_tool_call` is a fake recording function
- **WHEN** `chat_stream(..., on_tool_call=on_tool_call)` is called
- **THEN** `on_tool_call` is never invoked

#### Scenario: callback is NOT invoked when on_tool_call is None

- **GIVEN** a stream with `finish_reason == "tool_calls"`
- **AND** `on_tool_call` is `None`
- **WHEN** `chat_stream(...)` is called
- **THEN** no `AttributeError` is raised
- **AND** the stream completes normally

### Requirement: chat_stream accepts a tools catalog

`chat_stream` SHALL accept an optional `tools: list[dict] | None = None` parameter. When `tools is not None`, the worker MUST add `body["tools"] = tools` and `body["tool_choice"] = "auto"` to the outgoing JSON body. When `tools is None`, neither key appears (preserving v0.3.0 behavior).

`tools` list items are OpenAI-style tool definitions; the worker MUST forward them verbatim without validation.

#### Scenario: body contains tools when provided

- **GIVEN** `chat_stream(..., tools=[{"type": "function", "function": {"name": "shell_execute"}}])` is called
- **WHEN** `requests.post` is invoked
- **THEN** the JSON body has `body["tools"] == [{"type": "function", "function": {"name": "shell_execute"}}]`
- **AND** the JSON body has `body["tool_choice"] == "auto"`

#### Scenario: body has no tools key when None

- **GIVEN** `chat_stream(...)` is called with `tools=None`
- **WHEN** `requests.post` is invoked
- **THEN** the JSON body does NOT contain a `"tools"` key
- **AND** the JSON body does NOT contain a `"tool_choice"` key

### Requirement: chat_stream accumulates tool_call fragments by index

`chat_stream` MUST accumulate `delta.tool_calls` fragments across SSE chunks. The worker maintains a per-stream buffer `dict[int, dict]` keyed by `delta.tool_calls[].index`. For each fragment in `delta.tool_calls`:

| Field | Behavior |
|---|---|
| `id` | Stamped onto the entry once (subsequent overwrites ignored). |
| `function.name` | Stamped onto the entry once (subsequent overwrites ignored). |
| `function.arguments` | Concatenated as a string (this is what llama-server splits across chunks). |

When a chunk's `finish_reason == "tool_calls"`, the worker MUST, for each entry: `args = json.loads(entry["arguments"])`, with a `json.JSONDecodeError` fallback of `{"raw": entry["arguments"]}`. The buffer MUST be cleared before the next stream starts.

#### Scenario: arguments split across three chunks reassemble into one dict

- **GIVEN** three SSE chunks arriving in order:
  - chunk 1: `{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_x", "function": {"name": "shell_execute", "arguments": "{"}}]}}]}`
  - chunk 2: `{"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\"command\": \"ls\""}}]}}]}`
  - chunk 3: `{"choices": [{"finish_reason": "tool_calls", "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}}]}`
- **AND** `on_tool_call` is a fake recording function
- **WHEN** `chat_stream(..., on_tool_call=on_tool_call)` is called
- **THEN** `on_tool_call` is invoked exactly once
- **AND** the third argument is the dict `{"command": "ls"}` (reassembled, not a string)

#### Scenario: malformed JSON falls back to {"raw": ...}

- **GIVEN** a stream with a single tool_call whose accumulated `arguments` is `"not json {"` (invalid JSON)
- **WHEN** `finish_reason == "tool_calls"` is reached
- **THEN** the callback's third argument is `{"raw": "not json {"}`
- **AND** no `JSONDecodeError` propagates to the caller
