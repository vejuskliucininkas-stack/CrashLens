# CrashLens task queue

Shared between Claude, ChatGPT reviews and you. Newest decisions at the top of each
section. Review findings that need work get a task here with their R-ID.

## In progress

- T-11 Packaging, CI workflow, security pass and final documentation

## Next up

- T-12 First real run on Windows 11: `crashlens scan`, compare every check with
  Event Viewer / Device Manager / Settings, record wrong or missing data
- T-13 First ChatGPT review: `python scripts/make_review_packet.py --all`
- T-14 Non-English Windows: event messages are localised; verify parsing relies on
  event data fields, not English message text, wherever possible
- T-15 Kernel minidump: list loaded third-party drivers to point at likely culprits
- T-16 Optional: export report as PDF

## Done

- T-10 Review system for ChatGPT (this folder + scripts)
- T-09 Desktop app (Overview, Problems, Checks, Repairs, Report) and CLI
- T-08 Shareable reports (HTML/Markdown/JSON) with redaction
- T-07 Approval-gated repairs with audit log
- T-06 System health checks (disk, devices, updates, antivirus, startup, memory)
- T-05 Demo mode
- T-04 Crash analysis: blue screens, unexpected restarts, GPU resets, WHEA, app crashes
- T-03 Stop-code knowledge base
- T-02 Safe command runner (no shell, timeouts, fakeable)
- T-01 Project setup
