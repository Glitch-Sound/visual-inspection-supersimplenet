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
- 公開CLIやライブラリの入口はプロジェクト設定で定義し、業務処理は仕様・機能上の責務ごとに分ける。
- OpenSpecの仕様は「何を満たすか」、設計は「どのように満たすか」、タスクは「どの順で実装・検証するか」を扱う。
- 進行中の変更は `openspec/changes/<change-id>/`、正式仕様は `openspec/specs/<capability-path>/spec.md` に置く。

## アプリケーションの責務と配置

仕様、入出力、変更理由、既存の依存関係を確認し、独立して変更・検証しやすい責務を見つける。責務が明確になった能力の CLI 入口と処理を `src/app/<capability>/` にまとめる。小規模なプロジェクトでは、不要な階層や空の能力別パッケージを先に作らない。

- 複数の能力で実際に共有する設定、入出力契約、パス、実行基盤だけを `src/app/common/` に置く。推測による共通化、用途の曖昧な `utils.py`、細かすぎる分割を避ける。
- 能力間の直接 import は原則避け、受け渡す型、保存形式、パスなどの契約を明示する。`common/` は個別の能力へ依存させない。例外が必要なら理由と依存方向を記録する。
- 仕様の能力と Python パッケージは同じ数・名前である必要はない。責務と変更境界を照合して対応を文書化し、CLI、設定、成果物、境界を守るテストも示す。

構成を決める際は、責務の境界、共有する契約、依存方向、CLI・設定・成果物への影響、テストで守る境界を確認する。このプロジェクトでの具体的な配置は次に示す。

## 外観検査アプリの実装

`openspec/specs/visual-inspection/` の3つの正式仕様と実行時コードは次のように対応する。

| 正式仕様 | 実装パッケージ | 主な責務 |
| --- | --- | --- |
| `image-preparation/spec.md` | `src/app/image_preparation/` | `check`・`train-pre`・`test-pre`、位置合わせ、分割、準備 manifest |
| `model-training/spec.md` | `src/app/model_training/` | `train`、探索、学習、checkpoint と最良試行の保存 |
| `model-evaluation/spec.md` | `src/app/model_evaluation/` | `test`、checkpoint 推論、可視化、判定集約 |
| 3能力に共通する契約・実行基盤 | `src/app/common/` | 設定、保存先、manifest・結果の型、CLI 実行記録、画像入出力、学習成果物の復旧 |

各能力の CLI は自身の処理と `common/` を参照する。能力パッケージ間の直接 import と `common/` から能力への import は置かない。画像準備から学習へは `PreparationManifest`、学習から評価へは `BestTrialResult`、checkpoint、設定を既存の保存先で引き渡す。共有する型と検証規則は `common/contracts.py`、パスは `common/paths.py`、中断した学習成果物一式の復旧は `common/artifact_transaction.py` に置く。学習成果物の書込み処理は `model_training/artifacts.py` が担う。

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
