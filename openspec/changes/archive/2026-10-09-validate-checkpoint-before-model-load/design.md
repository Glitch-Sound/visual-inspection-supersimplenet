## 背景・前提

正式仕様 `visual-inspection/model-evaluation` の `REQ-016-S02` は、メタデータのない checkpoint を検査開始前に理由付きで拒否する。<br />
現行 CLI は最良試行結果を確認した後、`CheckpointPredictor` でモデルを構築・読込し、その後 `evaluate_model` で checkpoint メタデータを照合する。<br />
仕様上の条件は変えないため、差分 spec は `skip_specs: true` とする。

## 目標・対象外

### 目標

- モデル構築前に checkpoint の型番、スコア契約、暫定閾値を設定と照合する。
- 正常な検査の保存結果と CLI の終了契約を保つ。

### 対象外

- manifest、学習、分割判定の変更。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 処理フロー、失敗時の結果 | CLI の事前照合 | 1.1, 1.2, 2.1 | TC-001 | メタデータ欠落・不一致時のCLI実行とモデル未構築を確認 |
| AC-002 | 処理フロー、データ契約 | CLI と評価処理 | 1.1, 1.2, 2.1, 2.2 | TC-002 | 有効なcheckpointの既存評価テストと品質検査 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| CLI の事前照合 | 変更 | 型番設定、checkpoint | 成功時は照合済みメタデータ、失敗時は入力不備 | 既存のメタデータ読込と契約照合 | `model_evaluation/cli.py` に確定。CLI の実行順序を管理するため |
| 評価処理 | 変更 | 照合済みメタデータ、試験入力 | 従来どおりの結果 | `model_evaluation/evaluation.py` | 既存の直接呼出しも保つため、メタデータの任意受渡しに確定 |

### 処理フロー

1. `test` は既存の学習成果物復旧、設定読込、最良試行結果の照合を行う。
2. CLI が checkpoint メタデータを読み、型番・スコア契約・暫定閾値を設定と照合する。
3. 照合成功後に predictor を構築し、評価処理へ照合済みメタデータを渡す。
4. 評価処理は判定・可視化・保存を従来どおり実行する。直接呼出しでは従来どおり自らメタデータを読む。

### データ契約と状態

checkpoint、最良試行、結果JSON、設定の形式に変更はない。<br />
照合済みメタデータは呼出し中だけ受け渡し、永続化しない。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `test --model` | 運用者 → CLI | 型番、成果物 | 従来の結果と終了JSON | メタデータ欠落・不一致 → 理由付き入力不備、終了コード2、モデル未構築 | 正しい成果物へ差し替えて再実行 |

## 技術判断

### 判断: CLI での事前照合

- **状態**: 確定。
- **採用内容**: 既存の `load_checkpoint_metadata` と `validate_score_contract` を predictor 構築前に呼ぶ。評価処理には照合済みメタデータを任意引数で渡す。
- **根拠**: 既存の検証規則を共用し、正常経路で checkpoint のメタデータ読込を増やさずに順序を直せる。
- **代替案**: predictor 内で照合する案は設定契約を predictor に持ち込むため採用しない。
- **実装規則 / 不変条件**: CLI では照合失敗時に predictor を生成しない。評価処理を直接呼ぶ既存の経路は自身で照合する。
- **影響**: 正常時のCLI契約と成果物を維持する。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| メタデータ欠落 | 事前照合 | モデル未構築、結果未生成 | 欠落理由と終了コード2 | 既存の実行記録JSON | 正しいcheckpointを配置して再実行 |
| 型番・スコア契約・閾値不一致 | 事前照合 | モデル未構築、結果未生成 | 不一致項目と終了コード2 | 既存の実行記録JSON | 成果物を照合して再実行 |

## セキュリティ・性能・運用

checkpoint は既存方針どおり出所を確認したアプリ生成物を使用する。<br />
正常経路でのメタデータ読込回数は増やさない。

## 移行とロールバック

成果物形式と設定に変更がないため移行は不要。<br />
ロールバックはコードを戻すだけでよい。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | AC-001 | 該当なし | integration | 欠落または不一致メタデータで `test` を実行 | モデル未構築、理由付き終了コード2 | `tests/test_evaluation.py::test_test_cli_rejects_checkpoint_contract_before_model_construction` | はい | CLI の照合順序をテストダブルで確認 | なし | `openspec/changes/archive/2026-10-09-validate-checkpoint-before-model-load/evidence/acceptance.md` |
| TC-002 | AC-002 | 該当なし | integration | 一致するメタデータで `test` を実行 | 従来の出力JSONと成功終了、評価へ照合済みデータを渡す | `tests/test_evaluation.py::test_test_cli_validates_checkpoint_before_model_construction` | はい | CLI の正常経路をテストダブルで確認 | なし | `openspec/changes/archive/2026-10-09-validate-checkpoint-before-model-load/evidence/acceptance.md` |

## 網羅性確認

差分specはない。既存 `REQ-016-S01/S02` と `REQ-018-S06` の範囲を TC-001、TC-002 および既存テストで確認する。

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| AC-001 | 該当なし | 1 | なし | 対応済み |
| AC-002 | 該当なし | 1 | なし | 対応済み |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | メタデータ欠落・不一致のCLI入力 | TC-001 と対象pytest | なし | 検証済み | `openspec/changes/archive/2026-10-09-validate-checkpoint-before-model-load/evidence/acceptance.md` |
| AC-002 | 一致するcheckpointのCLI回帰 | TC-002 と `npm run check` | なし | 検証済み | `openspec/changes/archive/2026-10-09-validate-checkpoint-before-model-load/evidence/acceptance.md` |
