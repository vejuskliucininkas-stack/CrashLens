CrashLens is a Python 3.10+ app. Layers, from bottom to top:

```
gui/ (PySide6)        cli.py
      \                /
       environment.py  -- builds runner + system info + repair executor (real or demo)
       scanner.py      -- runs every check, isolates failures, reports progress
      /        |         \
checks/      repairs/     report/
crashes.py   catalog.py   export.py (HTML / Markdown / JSON)
health.py    executor.py  redact.py
events.py
minidump.py
stopcodes.py
      \        |
       core/runner.py  -- the ONLY place processes are started
       core/models.py  -- Finding, CheckResult, ScanReport, Severity
       core/platform.py
```

**Reading Windows data.** Every check reads data through `PsQuery` objects: fixed,
read-only PowerShell scripts that end in `ConvertTo-Json`. `run_ps_json()` turns
the output into Python lists. Nothing from outside (user input, event text, file
names) is ever put into a script. Each query carries an id (`#crashlens-query:<id>`
on its first line) so tests and demo mode can answer it with `FakeRunner`.

**Checks.** A `Check` subclass implements `collect(ctx) -> (findings, message)`.
`Check.run()` wraps it: timing, "not on Windows" handling, and turning any
exception into an `ERROR` result so one broken check never breaks a scan.
`CheckContext.cached()` lets several checks share one event-log query per scan.

- `crashes.py`: blue screens (Event 1001 + Kernel-Power 41 + Event 6008 +
  minidump headers merged into incidents and grouped by stop code), graphics
  driver resets (4101), WHEA hardware errors, application crashes (1000) and
  hangs (1002), reliability index.
- `health.py`: free space, physical disk health/wear/temperature, disk errors in
  the event log, devices with errors, uptime/memory/pending restart, last update,
  antivirus state (Security Center, read-only), startup programs.

**Findings** carry a severity, plain-language summary, evidence lines,
recommendations and `repair_ids` pointing into the repair catalog.

**Repairs.** `repairs/catalog.py` is a fixed list. Each repair either runs a
built-in Windows tool (SFC, DISM, chkdsk /scan, restore point) or opens a Windows
page (Device Manager, Windows Update, ...). `RepairExecutor.execute()` requires an
`Approval` from `ApprovalRegistry.grant()`: single use, tied to one repair, expires
after 10 minutes. The GUI grants one only after the approval dialog is confirmed;
the CLI only after the user types `RUN`. Admin tools started without admin rights
are launched in a separate console via Windows' UAC prompt. Every attempt is
written to an append-only audit log (`%LOCALAPPDATA%\CrashLens\audit.log`).

**Reports** are rendered from one dictionary (optionally redacted) into HTML
(self-contained, escaped, strict CSP), Markdown or JSON.

**Demo mode** (`--demo`) swaps in a `FakeRunner` loaded with a realistic fictional
PC and forces repairs into dry-run mode. It is how the app is developed and
tested off Windows.
