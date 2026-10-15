# Verification status

HPC MCP 0.2.0 has been tested on a single Linux HPC login node with a non-root user account.

- Local MCP tool discovery, JSON-RPC stdio interactions, read/write guards and opt-in foreground/background execution have been exercised.
- A private OpenAI Secure MCP Tunnel connection was exercised through ChatGPT. The v0.2.0 scheduler and site-tool additions have not yet been refreshed in the ChatGPT plugin's cached tool definitions.
- Per-user systemd persistence was tested on a host with `Linger=yes`.
- The scheduler adapters and site command registry passed **51 unit and integration tests**; adapter scheduler submissions and cancellations were mocked.
- Slurm and PBS scheduler adapters were tested with mock command responses (without real submissions or cancellations); **no live batch jobs have been submitted as part of these tests**.
- Site-specific Slurm binary resolution was checked on a cluster with a restricted Tunnel PATH; read-only job listing succeeded.
- `pytest` passed automated tests including mock Slurm/PBS scheduler commands and fixed site-tool registration on 2026-10-15.

Not verified: **PBS live compatibility on an OpenPBS/PBS Professional cluster**, real user-configured site command portability, and operation across different HPC sites: sustained cron watchdog persistence on a real `Linger=no` system, a separate Linux user and Tunnel pair, failover after reboot, and large concurrent workloads. The test suite uses simulated scheduler and service backends and must not be treated as proof of production security.

Sensitive host/user-specific operational notes belong in an untracked `docs/STATUS.local.md`, not in the public repository.
