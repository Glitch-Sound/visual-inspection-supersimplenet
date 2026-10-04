# プロジェクト構成

## 共通ディレクトリ

```text
project/
├── src/<package_name>/  # 実行時コード
├── tests/               # 自動テスト
├── scripts/             # 開発・運用の補助スクリプト
├── openspec/            # OpenSpecの共通基盤、仕様、change
│   ├── changes/         # 進行中の変更
│   ├── specs/           # 正式仕様
│   └── schemas/         # ワークフローと成果物雛形
├── pyproject.toml       # Pythonとツールの設定
├── AGENTS.md            # AI 開発エージェントの共通指示
├── CLAUDE.md            # Claude Code 用の共通指示入口
└── README.md            # 利用方法
```

## 配置原則

- 実行時コードは `src/<package_name>/`、テストは `tests/`、開発・運用用スクリプトは `scripts/` に置く。
- 公開CLIやライブラリの入口はプロジェクト設定で定義し、業務処理は責務ごとに分ける。
- OpenSpecの仕様は「何を満たすか」、設計は「どのように満たすか」、タスクは「どの順で実装・検証するか」を扱う。
- 進行中の変更は `openspec/changes/<change-id>/`、正式仕様は `openspec/specs/<capability-path>/spec.md` に置く。

## 複数 capability の構成

change は一回の変更計画、capability は継続管理する規範的な能力であり、一つのchangeで複数capabilityを追加・変更できる。分割は主な観測結果、責務、入出力、独立した変更・検証の境界を基準にする。実装ファイルや処理順だけを理由に分割しない。

例えばデータ処理を次の境界で管理できる。

| Capability | 主な入力 | 観測できる結果 | 独立した検証対象 |
| --- | --- | --- | --- |
| `data-processing/input-preparation` | 元データと準備条件 | 後続処理で使える入力と除外理由 | 入力検証、準備結果、元データの保持 |
| `data-processing/processing` | 準備済み入力と処理条件 | 再現可能な処理結果 | 処理規則、失敗時の状態、再実行 |
| `data-processing/result-reporting` | 処理結果 | 利用者が判断できる報告 | 表示・保存契約、未処理の扱い |

各パスの `spec.md` が一つのcapabilityである。親の `data-processing/` は名前空間であり、親仕様は自動生成されない。`data-processing/spec.md` を追加すれば独立した第4のcapabilityになるため、目次として作らない。

複数仕様を束ねる `openspec/specs/data-processing/README.md` は、次の内容を持つ非規範的な案内文書として作成する。

- 各capabilityの正式仕様へのリンクと提供する能力
- 分割理由と、入力・出力・検証対象の比較
- 仕様間で引き渡す入力・結果と、処理全体の関係
- 横断要件の正本と適用範囲、新しい要件の配置基準
- 利用手順や導入時のchangeへのリンク

同じ横断要件を複数の `spec.md` に複写しない。主な観測結果と責務を持つcapabilityへ置き、適用される処理と他仕様の入力・出力契約を説明する。独立した能力として管理する必要が生じた場合だけ、新しいcapabilityを検討する。案内文書には要件の正本が各 `spec.md` であることを明記し、既存仕様と異なる規範的な条件を追加しない。

## 命名規則

| 対象 | 規則 | 例 |
| --- | --- | --- |
| Pythonパッケージ・モジュール | 小文字の `snake_case` | `app_core`, `settings.py` |
| Python関数・変数 | `snake_case` | `load_settings` |
| Pythonクラス・型 | `PascalCase` | `AppSettings` |
| pytestファイル・関数 | `test_` 接頭辞 + `snake_case` | `test_feature_returns_result` |
| OpenSpec change / capability | `kebab-case` | `add-export`, `identity/user-auth` |
