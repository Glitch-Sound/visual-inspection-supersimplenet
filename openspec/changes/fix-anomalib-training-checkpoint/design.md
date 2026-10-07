## 背景・前提

`model_training.search` が元画像単位で集合を分離し、`trainer.py` が検証画像のフォルダをAnomalibに渡す。
現状の `from_test` と比率1.0は再分割を指示する。
`model_adapter.py` のモデルクラスは関数内で定義され、Lightningのcheckpoint保存時にpickleできない。
`predictor.py` のメタデータ読込は `weights_only=True` で、PreProcessorを含むcheckpointを拒否する。
推論本体とメタデータ保存処理は既に `weights_only=False` を指定する。

## 目標・対象外

### 目標

- 元画像単位の検証集合を全件検証に渡す。
- pickle可能なモデルクラスで学習率倍率とcheckpoint保存を維持する。
- アプリ生成checkpointのメタデータを読み込む。

### 対象外

- 依存関係の更新、探索条件、checkpoint形式の変更。
- 外部由来のcheckpointの安全な読込。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-014 | 業務フローと責務、技術判断 | 学習集合からAnomalib入力 | 1.1, 2.1 | TC-001 | Folder設定と集合の検証 |
| REQ-015 | 技術判断、データ契約と状態 | モデル生成からcheckpoint保存 | 1.2, 2.2 | TC-002 | pickleと学習率の検証 |
| REQ-016 | インターフェースと失敗時の結果 | checkpointから検査へ | 1.3, 2.3 | TC-003, TC-004 | メタデータ読込と欠落時拒否 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 検証画像の引き渡し | 変更 | `DatasetSplit` | 学習・検証データモジュール | Anomalib `Folder` | `trainer.py` に確定 |
| モデル生成 | 変更 | 特徴層、画像サイズ、学習率倍率 | 学習モデル | Anomalib `Supersimplenet` | `common/model_adapter.py` に確定 |
| メタデータ読込 | 変更 | アプリ生成checkpoint | 契約情報 | PyTorch | `model_evaluation/predictor.py` に確定 |

### 処理フロー

1. `search` が元画像単位で集合を分離し、`trainer` がそれぞれの分割画像を別フォルダへ配置する。
2. Anomalibには検証フォルダをそのまま検証集合として渡す。
3. モジュール直下のモデルクラスを試行ごとの倍率で構築し、Lightningがcheckpointを保存する。
4. 最良試行のcheckpointへ既存の契約情報を付け、検査側が読み込み照合する。
5. 契約不備なら検査前に拒否し、運用者が学習成果物を確認して再実行する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| `DatasetSplit` | なし | 学習・検証画像のpath集合 | 元画像単位で非重複 | `search` | 移行不要 |
| checkpoint | なし | `state_dict`、`visual_inspection`、PreProcessor等 | アプリ生成物だけを読込対象とする | Lightning、`artifacts` | 移行不要 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 学習 | CLI → trainer | 型番と準備manifest | checkpointと探索結果 | 集合不足や学習失敗 → 既存の終了コードと実行記録 | 既存の再開・restartを維持 |
| 検査 | CLI → predictor | アプリ生成checkpoint | 契約照合後の推論 | メタデータ欠落・不一致 → 検査前に拒否 | 正しい成果物で再実行 |

## 技術判断

### 判断・候補: 分離済み検証集合の利用

- **状態**: 確定
- **採用内容**: `Folder` の `val_split_mode="same_as_test"` とし、`val_split_ratio` は指定しない。
- **根拠**: `normal_test_dir` がアプリ側で分離済みの検証集合である。
- **代替案**: `from_test` は追加の分割を行うため採用しない。
- **実装規則 / 不変条件**: 検証画像を学習集合へ混入させない。
- **影響**: `trainer.py` のデータモジュール設定のみ。

### 判断・候補: checkpoint保存可能なモデル

- **状態**: 確定
- **採用内容**: `TunableSupersimplenet` をモジュール直下に置き、倍率をインスタンスに保持する。
- **根拠**: 関数内クラスはpickle不可。倍率は試行ごとに異なる。
- **代替案**: 標準モデルへ戻すと倍率を適用できない。
- **実装規則 / 不変条件**: adaptorとsegdecの既定学習率比、schedulerを維持する。
- **影響**: `common/model_adapter.py`。

### 判断・候補: checkpointメタデータ読込

- **状態**: 確定
- **採用内容**: メタデータ読込も `torch.load(..., weights_only=False)` を明示する。
- **根拠**: アプリが保存するcheckpointにはPreProcessorなどpickleオブジェクトが含まれる。既存の推論とメタデータ付与経路も同設定である。
- **代替案**: PyTorchの許可リスト追加はcheckpointに含まれるクラスごとに保守が必要。
- **実装規則 / 不変条件**: 信頼できるローカルのアプリ生成checkpointに限定し、契約照合を維持する。pickleの読込自体は契約照合より先に行われるため、出所不明のcheckpointを使わない。
- **影響**: `model_evaluation/predictor.py` と運用上の注意。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| メタデータ欠落 | predictor | 検査結果を作らない | 欠落理由を示すエラー | 既存のCLI実行記録 | 正しいcheckpointを用意 |
| 保存処理失敗 | trainer / artifacts | 最良成果物の更新を行わない | 処理失敗 | 既存のCLI実行記録 | 原因解消後に再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| セキュリティ | `weights_only=False` はアプリ生成の信頼できるcheckpointに限定 | 出所不明のcheckpointを配置しない運用 |
| 性能 | 検証画像の全件利用 | 既存の探索試行数と画像集合を維持 |
| 運用 | Ubuntu実機の学習・検査を確認 | スモーク試験記録 |

## 移行とロールバック

保存形式と設定形式は変えないためデータ移行は不要。
差し戻す場合はコードを元に戻し、失敗した試行を再実行する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-014 | REQ-014-S01 | unit / integration | 分離済み集合でrunnerを実行し、実Folderでも2件を渡す | `same_as_test`、比率指定なし、検証2件を保持 | `tests/test_training.py::test_trial_runner_uses_all_validation_images` | はい | テストダブルで引渡し、同ファイルの `test_anomalib_uses_complete_validation_folder` で実Anomalibの全件利用 | Ubuntu実機、3.1 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |
| TC-002 | REQ-015 | REQ-015-S01 | unit / integration | 倍率を変えたモデルを生成し、軽量な学習本体でLightningの1バッチ学習とcheckpoint保存を行う | pickle可能、両学習率に倍率適用、PreProcessor入りcheckpointを保存 | `tests/test_training.py::test_tunable_model_is_pickleable_and_uses_trial_multiplier` | はい | optimizer契約と同ファイルの `test_tunable_model_saves_lightning_checkpoint` で実Lightning保存経路。学習本体は軽量代替 | Ubuntu実機、3.2 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |
| TC-003 | REQ-016 | REQ-016-S01 | integration | PreProcessor入りcheckpointを保存して読込み、分割画像を検査する | メタデータ照合を通過し、結果JSONを生成 | `tests/test_evaluation.py::test_load_checkpoint_metadata_with_preprocessor` | はい | PyTorch実読込と同ファイルの `test_evaluation_starts_with_preprocessor_checkpoint` による検査処理。推論本体はテストダブル | Ubuntu実機、3.3 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |
| TC-004 | REQ-016 | REQ-016-S02 | unit | メタデータなしcheckpointを読込 | 理由付き拒否 | `tests/test_evaluation.py::test_load_checkpoint_metadata_rejects_missing_metadata` | はい | 不備の拒否 | Ubuntu実機、3.3 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-014 | 1 | 1 | なし | 網羅 |
| REQ-015 | 1 | 1 | なし | 網羅 |
| REQ-016 | 2 | 2 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 分離済み検証画像の全件利用 | TC-001、Ubuntuスモーク | Ubuntu実機 3.1 | 未検証 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |
| AC-002 | 倍率とcheckpoint保存 | TC-002、Ubuntuスモーク | Ubuntu実機 3.2 | 未検証 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |
| AC-003 | PreProcessor入りcheckpointの読込と契約照合 | TC-003、TC-004、Ubuntuスモーク | Ubuntu実機 3.3 | 未検証 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |
| AC-004 | Ubuntu 24.04 LTSの学習から検査 | `scripts/run_visual_inspection_smoke.py` | Ubuntu実機 3.4 | 未検証 | openspec/changes/fix-anomalib-training-checkpoint/evidence/acceptance.md |
