# Security policy

HPC MCP 0.3.0 is a research prototype without a guaranteed security-support window. The maintainer should publish a private security contact before accepting external users.

Do not publish credentials or exploitable details in a public issue. If no private channel is available, withhold sensitive reproduction steps until a secure reporting method has been established.

The default configuration is read-only. Opt-in command execution uses the current Linux UID; the executable allowlist and filesystem roots **do not isolate arbitrary commands**. Interpreters and build tools can read or write any resources available to that UID. Review the full [security model](docs/security.md) and your HPC site's policies before connecting a third-party agent.

Never run as root, never reuse another researcher's Tunnel credentials, and do not add private runtime configuration to version control.
