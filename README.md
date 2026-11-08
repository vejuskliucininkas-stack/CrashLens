# CrashLens

**Find out why your Windows 11 PC crashes, freezes or misbehaves - in plain language.**

CrashLens reads what Windows already records (the event log, crash dumps, device
and disk status), explains what it means, and suggests fixes. Repairs only run
after you approve each one, and scanning never changes anything.

> **Status: 0.1.0 - early version.** Developed and tested with recorded data; it has
> not yet been verified on a real Windows 11 PC. See [docs/STATUS.md](docs/STATUS.md).

## What it does

**Crash & blue screen analysis**
- Blue screens (BSODs) from the last 1-365 days, grouped by stop code, with a
  plain-language explanation, likely causes and next steps for 35+ stop codes
- Combines three sources so nothing is counted twice: BugCheck events, Kernel-Power 41
  and crash dump files (`C:\Windows\Minidump`)
- Unexpected restarts without a blue screen (power loss, freezes, forced power-off)
- Graphics driver resets, hardware (WHEA) errors
- Program crashes and freezes, grouped by program and faulting module, with hints
  ("the crash was inside the NVIDIA graphics driver")
- **What changed just before the crashes started**: driver installs, Windows
  updates and program installs in the 7 days before the first crash
- Windows updates that keep failing, with their error codes
- Windows' own reliability index

**System health scan**
- Free space on every drive; disk health, SSD wear and temperature
- Disk and file-system errors in the event log
- Devices with driver problems (Device Manager error codes, explained)
- Pending restarts, uptime, memory pressure
- How long since the last Windows update
- Whether virus protection is on and current (read-only)
- Number of startup programs

**Guided repairs - always with your approval**
- System File Checker, DISM check/scan/repair, read-only drive scan (`chkdsk /scan`),
  create a restore point, Windows Memory Diagnostic
- Shortcuts to Device Manager, Windows Update, Windows Security, Reliability Monitor,
  Startup apps and Storage settings
- Each repair shows exactly what will happen and the exact command; the Run button
  stays disabled until you confirm. Results are explained in plain language, and
  every repair is recorded in a history log.
- No repair deletes files, changes security settings or turns off protection.

**Reports to share**
- Save as a web page (HTML), Markdown (for forums) or JSON
- Personal details (user name, computer name, e-mails, serial numbers, profile paths)
  are removed by default

## Start it on Windows 11

1. Download the project as a ZIP (on GitHub: green **Code** button > **Download ZIP**)
   and unzip it, for example into your Documents folder.
2. Double-click **CrashLens.bat**.

That's it. The first start sets everything up by itself (1-3 minutes, needs
internet). If Python isn't installed yet, it offers to install it for you; after
that, double-click CrashLens.bat again. Every later start opens the app right away.

Tip: right-click CrashLens.bat > **Run as administrator** to let CrashLens read crash
dump files and disk wear. Everything else works without it.

When the GitHub build is active, a ready-made **CrashLens.exe** (no Python needed) is
available from the repository's **Actions** tab > latest "Build CrashLens.exe" run >
**Artifacts**.

### Manual setup (optional)

```
py -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui]"
crashlens            # the app
crashlens --demo     # the app with sample data
```

### Command line

```
crashlens scan                      # print all findings
crashlens scan --days 90 --json     # JSON, personal details removed
crashlens report report.html        # save a shareable report (.html / .md / .json)
crashlens repairs                   # list repairs
crashlens repair sfc_scan           # explains the repair, then asks you to type RUN
crashlens repair dism_restore --dry-run
crashlens audit                     # repair history
```

### Build a standalone .exe

```
pip install -e ".[gui,build]"
python packaging\build.py
```
This creates `dist\CrashLens\CrashLens.exe` (desktop app) and
`dist\crashlens-cli\crashlens-cli.exe` (command line).

## For developers

```
pip install -e ".[dev]"
pytest                    # 119 tests; GUI tests run headless
ruff check src tests      # lint
python scripts/secret_scan.py
```
Everything except live Windows queries can be developed on any OS using demo mode
and `FakeRunner`. On Windows, `pytest` additionally runs `tests/test_windows_live.py`,
which runs every check against the real system (read-only).

- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Security design: [docs/SECURITY.md](docs/SECURITY.md)
- Features done / known problems: [docs/STATUS.md](docs/STATUS.md)
- ChatGPT review workflow: [review/README.md](review/README.md)
- Task queue: [review/TASKS.md](review/TASKS.md)

## Where CrashLens keeps its files

`%LOCALAPPDATA%\CrashLens\audit.log` - the repair history. CrashLens writes nothing
else unless you save a report.
