# HPC MCP 運用手順：コマンド許可と Tunnel API キー更新

対象：HPC MCP v0.3.0、ユーザーごとの OpenAI Secure MCP Tunnel。
本書はohtakaでの運用例であり、HPC-MCPの汎用運用手順は[こちら](../../../docs/operations_JA.md)を参照する。RDCを使用しない運用を想定する。通常の Linux ユーザー権限で操作し、`sudo` は使用しない。

ohtaka (System B) を想定した構成例（各人の実際のパスに置換すること）：

- リポジトリ：`/path/to/hpc-mcp`
- 許可する作業領域：`/path/to/approved/work`
- 非公開ポリシー：`~/.config/hpc-mcp/config.toml`
- 非公開 API キー：`~/.config/hpc-mcp/tunnel.env`
- Tunnel Profile：`~/.config/tunnel-client/hpc-mcp.yaml`
- cron watchdog：`deploy/cron_watchdog.py`

**重要**：上記 `~/.config` 内の設定・認証情報は Git リポジトリの外に置く。API キーの値をチャット、ログ、Git、Issue に貼り付けないこと。

## 1. 権限の仕組み

権限は独立した三つの階層で管理される。

| 階層 | 管理場所 | 内容 |
| --- | --- | --- |
| ChatGPT のツール許可 | ChatGPT のプラグイン設定 | *公開された MCP ツール* の呼び出し確認・許可を管理 |
| MCP ツール公開 | `config.toml` の `[permissions]` | `execute_command`、書き込み、ジョブ投入・取消などを公開するか決める |
| コマンド許可リスト | `config.toml` の `[commands].allowlist` | `execute_command` が実行できる実行ファイル名を決める |

ChatGPT 側を「すべてのツールを許可」にしても、Linux 側の `allowlist` が広がるわけではない。

- `enable_commands = false` の場合、`execute_command` 自体が公開されない。
- `enable_commands = true` でも、`allowlist` にないコマンドは拒否される。
- `filesystem.roots` は MCP のファイル操作対象およびコマンドの `cwd` を制限するが、**起動したコマンドがアクセスする OS 上のパスは隔離しない**。

## 2. コマンドを追加・削除する手順

以下は ohtaka の SSH ターミナルで実行する（ChatGPT の MCP コマンドではない）。

### 2.1 現在の状態を確認

```bash
cd /path/to/hpc-mcp

./install.sh --service-status
.venv/bin/python deploy/cron_watchdog.py status
```

ChatGPT からは `list_allowed_commands()` で、現在の許可リストとサービスから見える実行ファイルの場所を確認できる。ただし、リストが表示されることと、プログラムの安全性は別問題である。

### 2.2 非公開設定をバックアップ

```bash
cp -p ~/.config/hpc-mcp/config.toml \
  ~/.config/hpc-mcp/config.toml.bak.$(date +%Y%m%d%H%M%S)
chmod 600 ~/.config/hpc-mcp/config.toml
```

### 2.3 `config.toml` を編集

```bash
vi ~/.config/hpc-mcp/config.toml
```

既存の `[permissions]` と `[commands]` に追記する。**同名の TOML セクションを重複して作らない**。

```toml
[filesystem]
roots = ["/path/to/approved/work"]

[permissions]
enable_writes = false
enable_commands = true
enable_scheduler_submit = false
enable_scheduler_cancel = false
enable_site_tools = false

[commands]
allowlist = [
  "hostname", "whoami", "pwd", "date", "uptime",
  "crontab", "python3"
]
env_allowlist = []

[scheduler]
type = "slurm"
```

これは抜粋例である。既存の `[limits]`、site-tools 設定、その他の項目は削除せず維持する。コマンドを追加するときは **既存の `allowlist` の要素を残して、必要な名前だけ追加**する。削除するときは該当要素だけ削除する。

ohtaka で観測された例では `python3` がユーザーの `~/.local/bin/python3` として検出された。利用される Python は MCP サービスの `PATH` に依存する。`.venv/bin/python` と同一とは限らない。

> **`cron` と `crontab` は異なる。** `crontab` は各ユーザーの定期実行設定を表示・変更するコマンド（例：`crontab -l`）である。cron デーモン `crond` の起動・停止に権限を与えるものではない。

### 2.4 設定の構文・読み込みを検査

```bash
cd /path/to/hpc-mcp

env -u PYTHONPATH .venv/bin/python -c \
  'from hpc_mcp.config import load_settings; s=load_settings(); print("Config OK:", s.allowed_commands)'
```

`Config OK` が表示されない場合は、再起動前に設定を修正する。変更前の状態へ戻す場合は、2.2 で作成したバックアップを使用する。

### 2.5 Tunnel を再起動する

**ohtaka の cron 管理の場合**：

```bash
cd /path/to/hpc-mcp

.venv/bin/python deploy/cron_watchdog.py stop
.venv/bin/python deploy/cron_watchdog.py start
.venv/bin/python deploy/cron_watchdog.py status
```

`"running": true` を確認する。再起動の数秒間は ChatGPT 接続が切れる場合がある。cron 管理自体がまだ有効でない場合は、サイトの常駐ポリシーを確認してから `./install.sh --activate --backend=cron` で有効化する。

**systemd --user で運用している環境の場合**：

```bash
systemctl --user restart hpc-mcp-tunnel.service
systemctl --user status hpc-mcp-tunnel.service
```

**手動起動の場合**：フォアグラウンドの `tunnel-client run` を終了し、設定済みの Profile で再実行する。

`cron` と `systemd` を同時に使用しない。ohtaka の `Linger=no` 環境では、cron バックエンドが利用可能でもログアウト・再起動後の常駐性は別途確認する。

### 2.6 ChatGPT から検証

1. `HPC MCP (ohtaka)` の `ping()`、`get_system_info()` を実行する。
2. `list_allowed_commands()` で更新後の `allowlist` を確認する。
3. `execute_command(argv=["python3", "--version"], cwd="/path/to/approved/work")` でバージョンを確認する。
4. `crontab` の状態を確認する場合は `execute_command(argv=["crontab", "-l"], cwd="/path/to/approved/work")` を実行する。crontab に認証情報を直接書かないこと。

**ツール一覧の更新が必要な場合**：`enable_commands`、`enable_writes`、`enable_scheduler_submit` などを変更して MCP ツールの公開・非公開が変わったときは、Tunnel 再起動後に ChatGPT の「Update tools / ツールを更新」を実行し、新規チャットで確認する。**既存の `execute_command` の `allowlist` だけを変更したときは、通常ツール一覧の更新は不要**（Tunnel 再起動は必要）。

## 3. Runtime API key の期限切れ・交換

`CONTROL_PLANE_API_KEY` は Tunnel クライアントが OpenAI Platform と通信するための秘密情報である。ChatGPT 側プラグインの「OAuth」や「すべてのツールを許可」とは別の設定である。

**通常は、同じ Tunnel ID / Profile / ChatGPT プラグインを継続使用できる。** API キーを交換するためだけに `tunnel-client init --force` やプラグイン再作成を行わない。

### 3.1 新しいキーを発行する

1. [OpenAI Platform: API keys](https://platform.openai.com/settings/organization/api-keys) で、対象の Platform organization を選択する。
2. 新しい **制限付き Runtime API key** を作成し、Tunnel の **Read + Use** 権限を付与する。Tunnel 管理権限や広範な API 権限は不要。
3. 有効期限と交換予定日を控える。キーの平文は安全な保管場所にのみ保存する。

推奨：古いキーの失効・期限切れ前に、新しいキーを用意して切り替える。古いキーが既に期限切れでも同じ手順で復旧できる。

### 3.2 ohtaka の秘密ファイルを編集

```bash
umask 077
vi ~/.config/hpc-mcp/tunnel.env
```

ファイル内の **既存の行を置き換える**（API キーの値をここや ChatGPT に書かないこと）。

```ini
CONTROL_PLANE_API_KEY=REPLACE_WITH_NEW_RUNTIME_KEY
```

```bash
chmod 600 ~/.config/hpc-mcp/tunnel.env
```

**禁止事項**：API キーをチャットに送る、`echo` や `cat` で端末に表示する、`curl` の URL やコマンド引数に含める、Git 管理下へコピーする。

### 3.3 必要に応じて診断する

`doctor` に環境変数を渡す場合は、キーを端末に表示せず一時的なサブシェルで読み込む。

```bash
(
  set -a
  . "$HOME/.config/hpc-mcp/tunnel.env"
  set +a
  "$HOME/.local/bin/tunnel-client" doctor --profile hpc-mcp --explain
)
```

上のサブシェル終了後は、そのキーが親シェルに残らない。診断ログを第三者に共有するときは、認証情報・識別情報が含まれていないか確認する。

### 3.4 Tunnel を再起動して新しいキーを反映

**cron 管理（ohtaka の例）**：

```bash
cd /path/to/hpc-mcp

.venv/bin/python deploy/cron_watchdog.py stop
.venv/bin/python deploy/cron_watchdog.py start
.venv/bin/python deploy/cron_watchdog.py status
```

**systemd 管理の場合**：

```bash
systemctl --user restart hpc-mcp-tunnel.service
```

手動起動では、実行中のクライアントを止め、更新した `tunnel.env` を新しいプロセスに読み込ませて再実行する。

### 3.5 動作確認と古いキーの廃止

ChatGPT の `HPC MCP (ohtaka)` から `ping()`、`get_system_info()`、`scheduler_list_jobs()` を順番に実行する。

- 成功：交換完了。旧キーがまだ有効なら Platform で失効させる。
- 認証失敗：Tunnel ID と組織・ChatGPT workspace の紐付け、新キーの **Read + Use** 権限、有効期限、`tunnel.env` の形式、Tunnel 再起動の有無を確認する。
- プラグインの「Update tools」は通常不要。API キーだけを交換しても MCP ツールの一覧は変わらない。

## 4. よくあるトラブル

| 症状 | 確認項目 |
| --- | --- |
| `Commands must use allowlisted names` | `argv[0]` は `./script` のようなパスではなく、許可された実行ファイル名か。専用スクリプトのパスをそのまま `argv[0]` に指定することはできない。 |
| `python3` を許可したのに目的の版が動かない | `list_allowed_commands()` の実体パスと `PATH`、Python バージョンを確認する。 |
| `Config OK` が出ない | TOML の重複セクション、カンマ、引用符、実在しない `filesystem.roots` を確認する。 |
| 許可変更が反映されない | 設定を保存したか、実際に動作中の Tunnel を再起動したか確認する。 |
| `ping()` が失敗 | Tunnel プロセス、cron watchdog、API キー有効期限、ネットワークを確認する。 |
| cron の `stop` 後に再起動した | cron watchdog は定期起動するため正常な挙動。常時停止したい場合は `./install.sh --remove-cron` を使う。 |
| ログアウト後に切断 | サイトのプロセス・cron 継続運用ポリシーを確認する。cron の設定だけで常駐が保証されるわけではない。 |

## 5. セキュリティ上の注意

- `python3`、`make`、`cmake`、`bash` などは任意のコードや外部コマンドを実行し得る。**コマンド名の allowlist は OS レベルのサンドボックスではない**。
- `crontab` は閲覧だけでなく定期実行設定の変更・削除も可能である。ChatGPT 側で「すべて許可」を有効にすると操作確認が省略される可能性があるため、破壊的操作は個別確認を推奨する。
- `sbatch` や `scancel` は一般コマンドの allowlist より、専用の `scheduler_submit_script` / `scheduler_cancel_job` と個別 opt-in を利用する。
- ohtaka のフロントエンドでは大規模ビルドや計算を実行しない。重い処理は Slurm 割当内で実行する。
- 秘密ファイル（`config.toml`、`tunnel.env`、Tunnel Profile）は非公開とし、アクセス権を 0600 に保つ。

## 6. 関連資料

- [Tunnel 設定](../../../docs/tunnel_setup.md)
- [systemd / cron 管理](../../../docs/service_backends.md)
- [開発・ビルドコマンド](../../../docs/development_commands.md)
- [Slurm / PBS とサイト固有ツール](../../../docs/schedulers_and_site_tools.md)
- [セキュリティ](../../../docs/security.md)
- [OpenAI Secure MCP Tunnel（公式）](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
