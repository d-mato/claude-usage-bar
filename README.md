# claude-usage-bar

macOS のメニューバーに Claude Code の使用量（5時間セッション / 週次）を％表示する SwiftBar プラグイン。

```
37% · 2h24m
```

- 左：現在の 5時間セッションでの使用率
- 右：そのセッションがリセットされるまでの残り時間

クリックすると詳細（5時間セッションと週次の％、リセット時刻、モデル別週次など）が表示されます。70% でオレンジ、90% で赤に変色。

## 仕組み

Claude Code 自身が `/usage` スラッシュコマンドで叩いている内部 API `https://api.anthropic.com/api/oauth/usage` を直接呼び出します。表示される値は `/usage` と完全一致します。

- 認証：macOS Keychain に保存された Claude Code の OAuth アクセストークン（`Claude Code-credentials`）を `security` コマンドで取得
- 集計：Anthropic 側でやってくれる（ローカル集計は不要）
- 依存：`jq`, `curl`, `security`（標準で入っている）

> [!NOTE]
> `/api/oauth/usage` は公式の公開 API ではなく Claude Code が内部利用しているエンドポイントです。Claude Code のバージョンアップで仕様変更・廃止される可能性があります。

## 必要なもの

- macOS（`security` コマンドが必要）
- Homebrew
- Claude Code にログイン済みであること（OAuth トークンが Keychain に保存されている状態）
- `jq`（`brew install jq`）

## セットアップ

```sh
brew install --cask swiftbar
brew install jq

# このリポジトリを任意の場所に clone
git clone <this-repo> ~/Projects/claude-usage-bar
chmod +x ~/Projects/claude-usage-bar/claude-usage.5m.sh

# SwiftBar のプラグインフォルダを設定
defaults write com.ameba.SwiftBar PluginDirectory "$HOME/Projects/claude-usage-bar"
open -a SwiftBar
```

### 初回起動時の Keychain 許可ダイアログ

SwiftBar が初めてこのプラグインを実行すると、macOS から以下のようなダイアログが出ます：

> 「SwiftBar」が、キーチェーン項目"Claude Code-credentials"にアクセスしようとしています。

**「常に許可」** をクリックしてください。1回許可すれば以降は出ません。「許可」だけだと毎回ダイアログが出るので注意。

## 表示形式

| 場所 | 内容 |
|---|---|
| メニューバー | `37% · 2h24m`（5時間セッションの使用率＋残り時間） |
| ドロップダウン | 5h セッション・週次（全モデル/Opus/Sonnet）の％とリセット時刻 |

## トラブルシュート

- **メニューバーに `Claude ⚠️` が出る**：ドロップダウンを開いてエラーメッセージを確認。多くの場合は Keychain 拒否か、トークン期限切れ。
- **`OAuth token expired`**：ターミナルで `claude` を起動して再ログイン。
- **`Keychain access denied`**：Keychain Access.app で `Claude Code-credentials` を選択し、アクセス制御タブで SwiftBar を許可リストに追加。
- **数値が古い**：メニュー > Refresh、または 5分待つ。`5m` 部分（ファイル名）を `1m` 等にリネームすれば更新間隔が変わる。

## 設定（任意）

```sh
mkdir -p ~/.config/claude-usage-bar
cp _config.sh.example ~/.config/claude-usage-bar/config.sh
```

`KEYCHAIN_ACCOUNT` を上書きすれば、`whoami` と異なるアカウント名で Keychain に保存されている場合に対応できます。

## 過去バージョン

- **v0.1**: `ccusage` 経由でローカルログを集計していた版。値が公式 `/usage` と数十%ずれるため廃止。
- **v0.2**: 公式 `/api/oauth/usage` 直叩きに刷新。
