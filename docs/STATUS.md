# CrashLens status

Version 0.1.0. Updated as work lands.

## How it has been tested

- 127 automated tests (unit, CLI, headless GUI) pass on Linux with recorded /
  fictional Windows data (`FakeRunner`, demo mode).
- **Not yet run on a real Windows 11 PC.** Two live tests
  (`tests/test_windows_live.py`) and a CI job on `windows-latest` are written to do
  that, but have not been executed yet.
- **Not yet reviewed by ChatGPT.** The review system is ready (`review/`); no
  review has been received.

## Completed features

Crash & stability
- [x] Blue screens from Event 1001, Kernel-Power 41 and minidump headers, merged
      into single incidents and grouped by stop code
- [x] Plain-language knowledge base for 35+ stop codes, with causes, steps and
      matching repairs
- [x] Unexpected restarts without a stop code (power loss / freeze / forced off)
- [x] Graphics driver resets (Event 4101)
- [x] WHEA hardware errors (fatal vs corrected; PCIe noise kept low)
- [x] Program crashes and freezes grouped by program + module, with module hints
      and exception-code explanations
- [x] Reliability index
- [x] Changes in the 7 days before the first crash (driver installs/removals,
      Windows updates, program installs/removals)
- [x] Failing Windows updates with error codes

System health
- [x] Free disk space per drive
- [x] Physical disk health, SSD wear, temperature, uncorrected errors
- [x] Disk / file-system errors from the event log
- [x] Devices with Device Manager error codes (explained)
- [x] Pending restart, uptime, memory pressure
- [x] Age of the last Windows update
- [x] Antivirus on/off and definitions (read-only)
- [x] Startup program count

Repairs
- [x] SFC, DISM (check / scan / restore), chkdsk /scan, restore point, Memory
      Diagnostic, and shortcuts to Windows tools
- [x] Single-use, expiring, repair-specific approvals; nothing runs without one
- [x] Non-admin repairs launched through UAC in a visible window
- [x] Plain-language result interpretation for SFC / DISM / chkdsk
- [x] Audit log and in-app history
- [x] Dry-run mode

Reports
- [x] HTML, Markdown, JSON
- [x] Personal-detail redaction on by default
- [x] Copy summary to clipboard

App
- [x] Beginner-first design: welcome screen, one-button check, plain-language
      verdict and problem cards with "Fix it" / "Tell me more", small things folded
- [x] Settings: light / dark / follow Windows, three text sizes, look-back period,
      expert mode (saved to %LOCALAPPDATA%\\CrashLens\\settings.json)
- [x] Logo and app icon
- [x] Pages: Home, Fix tools, Get help (reports), Settings, Details (experts only)
- [x] Background scanning with progress and cancel
- [x] Restart as administrator
- [x] Command-line interface
- [x] Demo mode with a realistic fictional PC
- [x] Standalone .exe build script (PyInstaller) - not yet test-built on Windows

Project
- [x] ChatGPT review workflow (packets, template, response tracking, optional API)
- [x] Secret scanner; CI workflow (Windows + Linux) - CI not yet run
- [x] Architecture, security and setup documentation

## Known problems and limits

1. **Unverified on real Windows.** PowerShell output shapes, property names and
   timings are based on documentation. Expect some checks to need adjustment after
   the first real run (task T-12).
2. **Localised Windows.** Blue-screen codes, parameters, dump paths and graphics
   driver names fall back to the untranslated event data fields when the message
   is not English (tested with German text). Not yet verified on a real
   non-English system (T-14).
3. **No culprit driver from dumps yet.** Only the dump header (stop code and
   parameters) is read; CrashLens does not yet list the drivers loaded at crash
   time (T-15).
4. **Elevated repairs report in their own window.** When CrashLens is not running
   as administrator, SFC/DISM output appears in the separate admin window and is
   not interpreted in the app. Running CrashLens as administrator avoids this.
5. **Restore points** need System Protection turned on, and Windows allows one
   new restore point per 24 hours by default; CrashLens reports the tool's message
   but does not yet explain these cases specifically.
6. **Disk health** depends on `Get-PhysicalDisk` / reliability counters; many
   USB enclosures and some RAID setups report nothing.
7. **Redaction is pattern-based**; review reports before posting publicly. IPv4
   addresses are not redacted.
8. **GitHub push not possible from the development session** (read-only access);
   commits are delivered as a git bundle until write access is granted.
9. No app icon, installer (MSI), code signing or auto-update yet.
10. No translations; English only.
