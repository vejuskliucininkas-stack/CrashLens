# Security and safety design

CrashLens runs with access to system information and can start Windows repair
tools, so it follows strict rules. Each rule is backed by code and, where
possible, by an automated test.

| Rule | How it is enforced | Test |
|---|---|---|
| Scanning never changes anything | Checks only run fixed read-only queries (`Get-*`, `Get-CimInstance`, `Get-WinEvent`, `Test-Path`) | `test_queries_are_fixed_and_bounded` |
| No shell injection | `SubprocessRunner` always passes an argument list with `shell=False`; PowerShell scripts are constants | `test_subprocess_runner_does_not_interpret_shell_metacharacters` |
| Every command has a timeout | `CommandRunner.run(timeout=...)`; queries 60-90 s, repairs per catalog | `test_subprocess_runner_real_process_and_timeout` |
| No repair without approval | `RepairExecutor.execute()` consumes a single-use, repair-specific, expiring approval | `test_repair_without_approval_is_refused`, `test_approval_is_single_use_and_specific`, `test_forged_and_expired_approvals_rejected` |
| GUI approval is explicit | Every fix opens a plain-language "Before we start" window; nothing runs unless "Yes, start" is clicked, and "No, go back" is the default button (Enter / Esc never start a fix) | `test_confirm_dialog_defaults_to_no`, `test_saying_no_runs_nothing` |
| CLI approval is explicit | User must type exactly `RUN`; anything else (including `yes`) cancels | `test_repair_cancelled_without_exact_word` |
| No destructive repairs | The catalog contains no delete/format/cleanup/registry/security-setting commands; `chkdsk` only with `/scan` | `test_catalog_commands_are_safe` |
| Never disable Windows security | No catalog entry touches security settings; antivirus check is read-only and only opens Windows Security | `test_catalog_commands_are_safe` |
| Elevation is visible | Non-admin repairs start through Windows' own UAC prompt in a visible console | `test_non_admin_uses_uac_window` |
| Audit trail | Approvals and results are appended to `audit.log` (only an 8-character token prefix is logged) | `test_runs_tool_and_interprets_sfc_output` |
| No user files deleted | Nothing in CrashLens deletes files. Reports refuse to overwrite unless confirmed (GUI save dialog / CLI `--force`) and are written atomically | `test_write_report_refuses_overwrite` |
| Private data stays private | Reports remove user name, computer name, profile paths, e-mails, MAC addresses, serials by default | `test_redactor`, `test_full_demo_report_all_formats` |
| Safe HTML reports | Every value is escaped; Content-Security-Policy `default-src 'none'`; no scripts | `test_html_escapes_everything` |
| Demo never touches the system | Demo mode forces dry-run repairs | `test_demo_repair_is_always_simulated` |
| No secrets in git | `.gitignore` covers key files; `scripts/secret_scan.py` runs in CI and before review packets are built | CI job `secret-scan` |

## Known limits

- Redaction is pattern-based. Review a report before posting it publicly.
- IPv4 addresses are not redacted (the pattern also matches version numbers).
- The approval registry lives in memory; approvals do not survive a restart, by design.

## Reporting a problem

Open an issue in the private repository, or note it in `review/TASKS.md`.
