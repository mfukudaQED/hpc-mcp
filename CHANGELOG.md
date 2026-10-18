# Changelog

All notable changes to HPC MCP are documented here. Releases follow a `vMAJOR.MINOR.PATCH` tag convention.

## [Unreleased]

## [0.3.0] - 2026-10-18

- Support explicit `./install.sh --python /path/to/python3.11` for new virtual environments, with checks for unsupported Python versions.
- Update installation and upgrade instructions, security-version references, and sanitize an example API-key placeholder.

- Integrate the optional, separately installed MCP File Manager for text browsing and editing through MCP Apps.
- Document File Manager opt-in permissions, Git history and UI usage.
- Add more development-command workflows and installation upgrade guidance.
- Separate machine-specific configuration and operations examples from the core documentation.

## [0.2.0] - 2026-10-15

- Initial public HPC MCP with per-user Secure MCP Tunnel setup.
- Read-only file, Git, system, and Slurm/PBS scheduler tools.
- Opt-in filesystem writes, allowlisted command execution, site-specific tools, and scheduler submission/cancellation.
- User-level systemd or cron service management.

**Release tag mapping:** `v0.2.0` marks the previously published `03cfb41551d05227d14391947a10f1c16354d8e3` commit. `v0.3.0` marks the new release-preparation commit. The initial project's package metadata was already `0.2.0`, so no retrospective `v0.1.0` tag is needed.

[0.2.0]: https://github.com/mfukudaQED/hpc-mcp/commit/03cfb41551d05227d14391947a10f1c16354d8e3
