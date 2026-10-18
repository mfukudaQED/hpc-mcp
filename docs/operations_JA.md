# HPC MCP 運用手順（日本語）

HPC MCPは一般ユーザー権限で導入・管理する。rootやsudoを使用しない。

## 設定と安全性

- 非公開設定: `~/.config/hpc-mcp/config.toml`
- Tunnel認証情報: `~/.config/hpc-mcp/tunnel.env`
- 書き込み・コマンド実行・ジョブ操作はそれぞれ明示的な許可が必要。
- `[commands].allowlist` は実行可能コマンド名の制限であってOSサンドボックスではない。Pythonやシェル等の許可は慎重に行う。
- `[filesystem].roots` はファイルツールとコマンドの作業ディレクトリを制約するが、子プロセスのOSアクセス権限は制約しない。

## 更新と再起動

既存環境の更新方法は[アップグレード手順](upgrading.md)を参照。設定を変更した場合は、
使用中のバックエンドだけを再起動し、公開ツールの構成が変わった場合はChatGPTの
**Update tools / Refresh tools**を行う。

- systemd user: `systemctl --user restart hpc-mcp-tunnel.service`
- cron watchdog: `.venv/bin/python deploy/cron_watchdog.py stop` に続けて同じスクリプトの `start`

cronとsystemdを同時に有効化しない。APIキーの更新は秘密ファイル内で行い、キーをコマンドライン、
チャット、Git、ログに表示・保存しない。Tunnel IDや認証情報を他の利用者と共有しない。

より詳細な[通信設定](tunnel_setup.md)、[サービス管理](service_backends.md)、
[セキュリティ](security.md)、[開発コマンド](development_commands.md)も参照。

サイト固有の実例は[sham](../examples/sites/sham/README.md)と
[ohtaka](../examples/sites/ohtaka/operations_JA.md)に分離している。
