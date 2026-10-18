# HPC MCP 設計書

**Version:** 0.2.0 (MVP)
**Target:** Linux/HPC (初期検証例: sham / Slurm。サイト固有設定は `examples/sites/` に分離)
**Date:** 2026-10-15

## 1. 目的

ChatGPTの通常チャット（PC/iPhone）から、研究者が自身のLinuxアカウント権限でHPCクラスターを操作できるMCPサーバーを提供する。Remote Desktop Commander (RDC) に依存せず、無料・Cloudflare不使用・VPS不使用・計算機側の新規受信ポート開放不要という方針を採用する。通信には OpenAI Secure MCP Tunnel の private/developer-mode 接続を使用する。Tunnelの使用料、権限、各利用者のアカウント適格性は運用前に個別に確認する。

**スコープの区別:** 本リポジトリはMCPサーバーを実装する。OpenAIのTunnelサービスは自前運用ではなく外部の通信中継基盤である。全体を「shamだけの物理計算機で自己完結」とは表現しない。

## 2. アーキテクチャ

```text
ChatGPT account A          ChatGPT account B
       |                           |
OpenAI Secure MCP Tunnel A   Secure MCP Tunnel B
       ^ HTTPS outbound           ^ HTTPS outbound
       |                           |
HPC host / Linux userA       HPC host / Linux userB
 tunnel-client A              tunnel-client B
       | stdio                      | stdio
 hpc-mcp A                    hpc-mcp B
       |                           |
Linux UID=A                   Linux UID=B
FS / Slurm / Git              FS / Slurm / Git
```

- MCPプロセス、Tunnel ID、Runtime API Key、設定、systemd user unitは**Linuxユーザーごとに独立**させる。
- MCPサーバーはstdioで起動し、TCPポートを公開しない。
- Tunnelクライアントは `api.openai.com:443` に外向きのHTTPS通信を行う。OpenAI側でTunnel/ChatGPT Workspaceの関連付けとRead+Use権限が必要。
- 管理者は導入マニュアルと共通ソースを配布するのみとし、利用者のAPIキーやSSH秘密鍵を保持しない。
- 利用者間でTunnel IDを共有しない。Tunnel登録とMCP内部のOSユーザー分離は別の安全境界である。
- Secure MCP Tunnelは private/developer-mode接続用。**公開プラグイン配布には利用できない**。公開予定なのは本実装のソースコードと導入方法である。

## 3. ユーザーストーリー

1. 研究者が自分のTunnelを作成し、自分のHPCアカウントに導入する。
2. iPhone/PCの個人ChatGPTから `get_system_info` を呼び出し、本人のUIDとhostnameを確認する。
3. 許可された `~/work` 以下のソースを閲覧・検索する。
4. 明示的なローカル設定変更後、差分編集とコマンド実行を利用する。
5. Slurmの自己ジョブを確認し、必要に応じ本人がレビューした `sbatch` スクリプトを投入する。

## 4. ツールセットと権限

### MVP (実装済み)

| ツール | デフォルト | 制約 |
|---|---|---|
| `ping`, `get_system_info` | 有効 | 読み取り専用 |
| `list_directory_tool`, `read_file_tool`, `search_files_tool` | 有効 | 許可ルート、秘密ファイル除外、サイズ上限 |
| `slurm_list_jobs` | 有効 | OSユーザー自身のジョブ |
| `git_status_tool`, `git_diff_tool` | 有効 | 許可ルート、出力上限 |
| `write_file_tool`, `replace_text_tool` | 既定無効 | 原子的更新、既存ファイルのSHA-256一致が必須 |
| `execute_command` | 既定無効 | シェル不使用、allowlist、timeout |
| `start_background_process`, `read_background_output`, `terminate_background_process` | 既定無効 | ユーザー所有プロセス、セッションIDと開始時刻の照合 |
| `submit_slurm_script` | 既定無効 | 既存ファイルのみ、Slurm権限、明示設定 |

### 後続バージョン (未実装)

- Slurm/PBS 共通アダプターに追加したジョブ取消・詳細取得の改良と、サイト固有書式の検証。
- diff/patch適用、コンパイル結果の診断、Git commit/push等の高リスク操作。
- PTYを伴うインタラクティブセッション、厳密なジョブ終了コード保存、ログローテーション。
- Linux namespace/cgroupや専用コンテナによる強制隔離。
- マルチユーザー共通Gateway方式・OAuthによるUID連携 (現バージョンでは採用しない)。

## 5. 権限と脅威モデル

- OS UIDを唯一のファイル・ジョブ権限境界とし、MCP自体はrootで起動しない。
- `filesystem.roots` をcanonical pathで検証し、ルート外への `../`、外部へのsymlinkを拒否する。
- `.ssh`、`.config`、`.env`、秘密鍵拡張子を拒否する。これは完全な秘密検出ではなく補助的な拒否規則である。
- 任意コマンドが許可されると、ファイル用ルート制約や秘密名の拒否規則を迂回できる。`enable_commands=true` は**当該Linux UIDの広範囲の権限をChatGPT接続へ委任する**操作である。特に `python`, `bash`, `make`, `git`, `find` 等は任意コード/間接的なコマンドを実行できるため、basename allowlist はセキュリティサンドボックスではない。
- 読み込んだソースやログに含まれる指示は不信なデータである。モデルへのプロンプトインジェクションを想定する。
- APIキーは user-onlyの権限 (0600) で管理し、ログ、ソース管理、チャットへ渡さない。
- stdioのstdoutにはMCPフレーム以外を書かず、診断はstderrを使う。
- 監査は将来の課題。MVPのログはTunnelとsystemdに依存し、個別ツールの監査台帳は未実装。
- オペレーターは導入前に大学/研究所の運用規則、および外部AIへの研究データ送信条件を確認する。

## 6. 非機能要件

- stdio transport / Python 3.11+ / 既存Slurm CLI依存。
- 読込最大2 MiB/ファイル、出力最大16,000文字、1コマンド最大30秒、同時バックグラウンドプロセス最大4 (既定)。
- systemd --userのCPUQuota=10%, MemoryMax=512M, TasksMax=64をベースラインとする。これらはTunnelサービス自身の制限であり、Slurmに投入された計算ジョブは対象外。
- 認証失敗、通信停止、再起動時にも秘密情報を標準出力に表示しない。
- テストは設定境界、symlink逃避、hash競合、コマンド禁止、MCP tool discovery、Slurm CLIの実行確認に分ける。

## 7. 展開計画と受入基準

| Phase | 範囲 | 完了条件 |
|---|---|---|
| 1 | 本リポジトリ実装 | pytest合格、stdio tools/list成功 |
| 2 | 個人Tunnel導入 | `doctor` healthy、ChatGPT iPhoneから `get_system_info` 成功 |
| 3 | 書込とCLI | Git差分・ファイル編集・短いプログラムの実行テスト |
| 4 | Slurmとプロセス | 自分のジョブ投入とログ追跡、再起動後の状態確認 |
| 5 | 研究者への配布 | 他のLinuxユーザーと独立ChatGPT/Tunnelを用いたUID分離テスト |

## 8. 制約・未確定事項

- OpenAI PlatformでTunnel IDとRuntime API Keyを各ユーザーが用意する必要がある。
- Tunnelの料金・利用可否は各アカウントで確認する。無料であることは未確認。
- 対象クラスタから `api.openai.com:443` の実際のTunnel APIにアクセスできるかは、APIキー付きの `tunnel-client doctor` で確認する。`curl` の単純なHTTP応答だけでは接続可否を確定できない。
- APIキー未提供時には**リモートTunnelからの接続試験は行わない**。

## 9. 公式参照

- https://developers.openai.com/plugins/quickstart
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://github.com/openai/tunnel-client
- https://github.com/modelcontextprotocol/python-sdk

## 追記：スケジューラとサイト固有コマンド（v0.2.0）

v0.2.0 では Slurm と PBS/OpenPBS の共通 Scheduler Adapter を追加した。
設定 `[scheduler] type` でマシンごとに選択できる。
`scheduler_list_jobs` / `scheduler_job_detail` は参照専用で、
ジョブ投入と削除には個別の権限許可が必要となる。
また、ローカル設定 `[site_tools.NAME]` で、固定引数のサイト固有
照会コマンドを MCP ツールとして追加できる。
これらはサイト側の OS・ジョブスケジューラ権限を越えるものではない。
詳細は `docs/schedulers_and_site_tools.md` を参照。
