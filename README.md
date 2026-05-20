# claude-usage-bar

macOS のメニューバーに Claude Code の使用量（5時間ブロック / 週次）を％表示する SwiftBar プラグイン。

```
15% · 2h07m
```

- 左：現在の 5時間ブロックでの消費トークン率
- 右：そのブロックがリセットされるまでの残り時間

クリックすると詳細（5時間ブロックの消費トークン数・コスト・予測値、そして週次の使用量と％）が表示されます。70% でオレンジ、90% で赤に変色。

## 仕組み

- [SwiftBar](https://github.com/swiftbar/SwiftBar) がプラグインを定期実行してメニューバーに出力
- [ccusage](https://github.com/ryoppippi/ccusage) が `~/.claude/projects/` 配下のローカルログから使用量を集計
- Anthropic 側に問い合わせはしません（API キー不要）

## 必要なもの

- macOS
- Homebrew
- Node.js（`npx` が使えればよい）
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

初回起動時に SwiftBar からアクセシビリティ等の許可ダイアログが出る場合があります。

## 上限値の調整

Anthropic は各プランの正確なトークン上限を公開していないため、コミュニティ観測値をデフォルトにしています（Claude Max $100 想定）。実際に rate-limit に当たる点とずれていたら調整してください。

```sh
mkdir -p ~/.config/claude-usage-bar
cp _config.sh.example ~/.config/claude-usage-bar/config.sh
$EDITOR ~/.config/claude-usage-bar/config.sh
```

設定ファイル内：

| 変数 | デフォルト | 意味 |
|---|---|---|
| `BLOCK_TOKEN_LIMIT` | `220000000` | 5時間ブロックのトークン上限 |
| `WEEKLY_TOKEN_LIMIT` | `1000000000` | 週次のトークン上限 |

数日運用して「実際に頭打ちになった時点の％」を見ながらキャリブレーションするのが推奨。

## 表示形式

| 場所 | 内容 |
|---|---|
| メニューバー | `H:xx% W:xx%`（合算最大ステータスで配色） |
| ドロップダウン | 5時間ブロックの詳細（消費・コスト・予測・残り時間）と週次の詳細 |

## トラブルシュート

- **メニューバーに何も出ない**：SwiftBar の Preferences → Plugin Folder がこのディレクトリを指しているか確認。`claude-usage.5m.sh` が実行可能（`chmod +x`）か確認。
- **`node not found` / `jq not found`**：プラグインスクリプト先頭の `PATH` を環境に合わせて編集。
- **数値が古い**：メニュー > Refresh、または 5分待つ。`5m` 部分を `1m` などに変えれば更新間隔も変えられる（ファイル名のリネームのみ）。

## 制限事項

- Anthropic 公式のリアルタイム残量 API は提供されていないため、トークン消費から「推定％」を計算しています。Claude Code 内蔵の `/usage` 表示と完全に一致するわけではありません。
- 複数マシンで Claude Code を使っている場合、ローカルログには「このマシンの使用分」しか含まれません。
