CrashLens non-negotiables (treat any breach as Critical):

- No repair may run without an explicit, single-use approval from the user.
- No code path may delete, overwrite or move user files. (Writing a report to a
  path the user picked is allowed; replacing an existing file needs confirmation.)
- CrashLens must never disable or weaken Windows security features (Defender,
  firewall, UAC, Memory Integrity, SmartScreen, etc.).
- No shell strings: external commands are argument lists built from constants.
  Nothing typed by the user, read from the event log or from files may be placed
  into a command or a PowerShell script.
- Scanning is read-only.
- Shared reports must not contain the user name, computer name, e-mail addresses
  or serial numbers when "remove personal details" is on.
- No secrets in the repository.

Context reviewers should know:

- Development happens on Linux; nothing has been run on real Windows yet. Windows
  behaviour is reasoned from documentation and tested with recorded/fake data.
  Findings about real-Windows behaviour (output formats, localisation, encodings,
  permissions) are especially valuable.
- Windows data is read through fixed PowerShell queries returning JSON
  (`core/runner.py`, `checks/*.py`). Tests use `FakeRunner` with canned JSON.

Severity scale for findings: Critical, High, Medium, Low, Suggestion.
