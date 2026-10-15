# Optional assisted installation with Remote Desktop Commander

Users who already have a functioning **Remote Desktop Commander (RDC)** connection to their own Linux account may ask ChatGPT to inspect the host and assist with setting up HPC MCP. This is an **optional bootstrap path**, not a requirement. RDC is a separate third-party integration and may have its own plan, installation, access, or usage limits.

## Suggested workflow

1. Connect RDC to your normal, non-root Linux account and verify the host and user.
2. Ask ChatGPT to inspect Python, `git`, user-level `systemd`, `loginctl` Linger status, `crontab`, and Slurm availability; install HPC MCP in a **user-owned** directory.
3. Ask ChatGPT to run the automated local tests, check the example policy, and prepare the user service or cron backend. Review file changes and commands before approving them.
4. **Complete the Platform and ChatGPT setup yourself:** create/authorize the private Tunnel, prepare a **restricted runtime API key**, and create the ChatGPT custom MCP plugin following [Tunnel setup](tunnel_setup.md). Never disclose a runtime key to ChatGPT or RDC. Enter credentials privately using your local terminal/editor.
5. Ask ChatGPT to verify the Tunnel health and the plugin's read-only tools. After optional commands are enabled, refresh the plugin's tool list in ChatGPT.
6. Once the private HPC MCP works independently (including from a **new** chat), RDC can be disabled if desired. Test again to ensure no dependency on RDC remains.

A sample ChatGPT request (without credentials):

> Using the RDC connection to my Linux account, inspect the environment and help install the public HPC MCP project as my unprivileged user. Do not use sudo, change system-wide configuration, install a background service until I approve, or read or print credentials. Follow docs/tunnel_setup.md and docs/service_backends.md. Leave the private API key and ChatGPT plugin authorization steps to me. Run tests, then report the commands and files modified.

ChatGPT may perform permitted filesystem and service tasks through RDC **when that connector is configured, online and authorized**. It cannot necessarily create your Platform organization permissions, restricted API key, or ChatGPT plugin automatically. Do not imply those private account actions are delegated.

**HPC security:** Ask your site's administrator about its policy for outbound third-party connections, persistent user services, and research data handling. A command-enabled MCP server is not isolated from the ordinary account's accessible files.
