# Verification status

HPC MCP **0.3.0** remains a research prototype. Verification below distinguishes
automated tests from actual cluster or ChatGPT host tests.

## Verified

- A per-user MCP connection over a private Secure MCP Tunnel has been tested
  in ChatGPT on a Linux HPC login node.
- Core read tools, opt-in command tools, Git tools, scheduler read operations,
  and user-managed Tunnel lifecycle have been exercised in development.
- Slurm/PBS scheduler adapter behavior and site-tool registration are exercised
  using mocked scheduler/site command responses. They are not evidence of
  production PBS compatibility.
- The optional MCP File Manager extension has registration/configuration tests.
  File Manager UI v16 was interactively verified in ChatGPT with an initial
  collapsed Explorer and a right-hand tab on ohtaka.
- On 2026-10-18, the HPC-MCP Python test suite passed **64 tests**
  in the ohtaka development environment, after moving the unrelated monitoring tests to HPC-PerfDiag. This count is a dated observation,
  not a guarantee for every subsequent change.

## Not yet verified across environments

- Live PBS/OpenPBS scheduler compatibility and portable site-command execution.
- Multiple independent HPC sites, users, Tunnel identities and failover.
- Sustained cron persistence on all `Linger=no` environments and reboot recovery.
- Production hardening and exhaustive security guarantees for command execution.

The example configurations under `examples/sites/` are machine-specific and
may require adaptation. Private user credentials and operational logs are not
part of this repository.
