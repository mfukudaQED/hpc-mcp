# Contributing

Contributions and bug reports are welcome. Please open an issue before proposing broad architectural changes.

## Local checks

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Keep new functionality behind opt-in permissions where it can modify files, execute programs, start background processes or submit Slurm jobs. Add tests for permission boundaries and failures. All scripts must operate without root privileges.

Never include real credentials, private Tunnel IDs, host profiles, home-directory configuration, unpublished research data, logs, or user-identifying HPC output in issues, patches, or test fixtures. Use anonymized paths and placeholders.

Review upstream MCP and Tunnel API changes before changing transports or integration behavior. For security-sensitive issues, do not disclose working exploits in a public issue; contact the maintainer privately.
