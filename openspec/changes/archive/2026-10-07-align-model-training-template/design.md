## 背景・前提

型番別設定の読込みは `src/app/common/config.py`、探索は `src/app/model_training/search.py`、画像拡張は `src/app/model_training/augmentation.py` が担当する。
利用者が更新した `config/part_XX.json` をひな形の正とする。
学習仕様の `REQ-005` と `REQ-006` は旧値を規定している。

## 目標・対象外

### 目標

- ひな形、設定省略時の既定値、テスト用設定、正式仕様の探索条件を一致させる。
- blurをひな形で無効にし、明示的な有効化で既存の拡張処理を使用できる状態を維持する。

### 対象外

- 探索・拡張アルゴリズムの変更。
- 既存の型番別設定と成果物の自動更新。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-005 | 業務フローと責務、データ契約と状態 | 型番別設定→探索 | 1.1、1.2、2.1 | TC-001、TC-002、TC-003 | ひな形値、設定既定値、10試行の結果と指標表示をpytestで確認 |
| REQ-006 | 業務フローと責務、データ契約と状態 | 型番別設定→学習時拡張 | 1.1、1.2、2.1 | TC-004、TC-005 | blur初期無効と有効化時の学習適用、検証時の不変をpytestで確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 設定ひな形 | 変更済み | 運用者の複製・編集 | 新規型番の初期条件 | 設定読込み | `config/part_XX.json`。利用者の編集を保持 |
| 設定読込み | 変更 | ひな形または型番別設定 | 型付き探索・拡張設定 | 探索、拡張 | `src/app/common/config.py` の省略時既定値を一致させる |
| 探索・拡張 | 維持 | 型付き設定 | 探索履歴、学習入力 | モデル学習 | 現行処理が設定値を消費することを確認済み |

### 処理フロー

1. 運用者がひな形を複製し、必要なら有効な値へ編集する。
2. 設定読込みで明示値を優先し、省略可能項目には既定値を適用する。
3. 学習時に設定された候補と試行回数で探索する。blurが無効ならblurを適用せず、有効なら設定された確率と強度で学習入力にだけ適用する。
4. 不正な設定は既存の検証で学習開始前に拒否する。修正して再実行できる。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番別設定ひな形 | 変更済み | `epochs.choices: list[int]`、`pruner.warmup_epochs: int`、`execution.trials: int`、`blur.enabled: bool` | `[100,200,300]`、40、10、false | 運用者 | 既存型番設定は変更しない |
| 省略時設定 | 変更 | `warmup_epochs: int`、`trials: int`、`blur.enabled: bool` | 40、10、false | 設定読込み | 明示値は従来どおり優先 |
| 探索履歴・checkpoint | 変更なし | 既存契約 | 新規学習の条件のみ変化 | 学習処理 | 既存成果物を移行しない |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train --model` | 運用者 → 学習 | 型番別設定 | 指定条件の探索履歴と成果物 | 不正設定→項目名を示して学習前に拒否 | 修正後に再実行。既存の再開規則を維持 |

## 技術判断

### 判断: ひな形と設定省略時の値を同期する

- **状態**: 確定
- **採用内容**: 利用者が編集したひな形を保持し、省略時のwarmup、試行回数、blurの有効状態をコード既定値に反映する。
- **根拠**: 明示値を持つ既存型番の互換性を維持しつつ、ひな形と省略時設定の食い違いをなくす。
- **代替案**: 明示値のみ変更する案は、省略時に旧値を残すため不採用。
- **実装規則 / 不変条件**: CLI形式、探索・拡張アルゴリズム、既存の設定・成果物は変更しない。
- **影響**: ひな形、新規に省略値を使う設定、テスト用設定と自動テスト。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 既存型番が旧条件を明示 | 設定読込み | 明示値を維持 | 従来条件で実行 | 探索履歴 | 必要な場合だけ運用者が設定を編集 |
| 不正な候補または試行回数 | 設定読込み | 学習を開始しない | 不正項目を示すエラー | 既存ログ | 設定修正後に再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 性能 | ひな形の試行回数と候補が変わる | 探索履歴に指定された10試行と条件を記録 |
| 運用 | 既存成果物を維持 | ファイル差分と試験で移行処理がないことを確認 |

## 移行とロールバック

既存の型番別設定と成果物に移行は不要である。
新条件を使う場合は運用者がひな形から新規設定を作成するか、既存設定を明示的に編集する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-005 | REQ-005-S01 | unit | ひな形と省略値を読み込む | 候補100・200・300、warmup40、試行10 | `tests/test_config.py::test_training_template_matches_defaults` | はい | 設定読込み、開発環境 | なし | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |
| TC-002 | REQ-005 | REQ-005-S01 | integration | テスト用設定で探索を実行 | 10試行と最良試行を記録 | `tests/test_training.py::test_search_selects_lowest_validation_percentile` | はい | 探索、軽量runner、開発環境 | なし | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |
| TC-003 | REQ-005 | REQ-005-S02 | unit | 探索結果を表示 | 暫定指標と表示 | `tests/test_training.py::test_search_report_labels_objective_as_provisional` | はい | 表示契約、開発環境 | なし | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |
| TC-004 | REQ-006 | REQ-006-S01 | unit | ひな形と値をそろえたテスト用設定のblurを読み、有効化して学習拡張を実行 | 初期無効。有効化で学習入力のみ変化 | `tests/test_training.py::test_blur_template_default_and_opt_in` | はい | 拡張処理、開発環境 | なし | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |
| TC-005 | REQ-006 | REQ-006-S02 | unit | 検証入力へ拡張を適用 | 入力不変 | `tests/test_training.py::test_validation_pipeline_disables_augmentation` | はい | 検証経路、開発環境 | なし | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-005 | 2 | 3 | なし | 網羅 |
| REQ-006 | 2 | 2 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 開発環境での設定読込みと軽量探索 | TC-001、TC-002 | なし | 検証済み | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |
| AC-002 | 開発環境でのblur初期状態と学習時拡張 | TC-004、TC-005 | なし | 検証済み | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |
| AC-003 | ひな形、仕様、既存成果物の扱い | 差分レビューと品質検査 | なし | 検証済み | openspec/changes/archive/2026-10-07-align-model-training-template/evidence/acceptance.md |
