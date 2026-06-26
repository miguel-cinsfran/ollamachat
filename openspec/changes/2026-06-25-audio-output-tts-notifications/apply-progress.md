# Apply Progress: Audio Output (TTS on demand + SAPI + Notifications + Sounds)

## WU-1 (2026-06-25)
- Status: complete
- Commit: acadd39
- Tasks: T1A–T1M
- Tests: 757 passing, 14 skipped (WSL)
- Notes: All core modules implemented and tested. WU-2 (UI + wx-tests) pending.

## WU-2 (2026-06-25)
- Status: complete
- Tasks: T2A–T2K
- Tests: 778 passing, 15 skipped (WSL)
- Notes: All UI modules implemented. VoiceDialog + WxToastSender + Audio tab in preferences + notifier wiring at 5 event sites + F8 handler (read selected message via system voice). All new wx-runtime tests use importorskip("wx").
