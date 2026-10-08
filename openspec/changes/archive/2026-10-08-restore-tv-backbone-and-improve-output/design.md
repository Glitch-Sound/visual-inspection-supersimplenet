## 背景・前提

学習と検査は`src/app/common/model_adapter.py`のモデル生成入口を共有する。checkpointの独自メタデータにはバックボーン識別子がない。Optunaの試行値は`search.py`で確定するが、CLIは試行条件を表示していない。検査は`evaluation.py`で分割ごとに結果画像を保存し、異常時だけ元画像へ色を重ねる。

## 目標・対象外

### 目標

- 共通モデル生成を`tv_in1k`に戻し、全型番を再学習する移行手順を記す。
- 異常分割の結果画像を元画像と既存の重ね合わせ画像の左右2面にする。
- 各試行開始時の条件表と終了状態を標準エラーに出し、標準出力JSONを維持する。

### 対象外

- 既存checkpointの自動識別・変換、探索空間、画像の色尺度、判定規則の変更。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-020 | 技術判断、移行とロールバック | 共通モデル生成と運用 | 1.1, 1.2, 4.1 | TC-001, TC-002 | 重み指定・restart自動試験と実学習 |
| REQ-010 | 業務フローと責務、技術判断 | 分割結果画像 | 2.1, 2.2, 4.1 | TC-003, TC-004, TC-005, TC-006 | 固定画像の画素・サイズ検査と実画像 |
| NREQ-004 | 業務フローと責務、技術判断 | 探索からCLIへの通知 | 3.1, 3.2, 4.1 | TC-007, TC-008, TC-009 | 状態別・再開時の表示試験と端末確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| モデル生成 | 変更 | 特徴層と画像サイズ | `tv_in1k`の特徴抽出器 | Anomalib / timm | 共有入口`common/model_adapter.py`に確定 |
| 分割結果の可視化 | 変更 | 分割画像、予測、閾値 | 異常時だけ横幅2倍の結果画像 | OpenCV、画像IO | `model_evaluation/evaluation.py`に確定 |
| 試行通知 | 追加 | 試行番号、選択値、状態、指標 | CLIへ通知 | Optuna | `model_training/search.py`の任意コールバックに確定 |
| 試行表示 | 追加 | 通知値 | 標準エラーへの条件表と結果 | Rich | `model_training/cli.py`に確定 |

### 処理フロー

1. 運用者が`train --restart`を実行し、対象型番の旧探索領域とcheckpointを削除する。準備済み画像と設定は保持する。
2. 学習CLIはデータ分割後、固定バックボーン、学習・検証画像数、既存試行数、今回の試行数を表示する。
3. 各試行でOptunaが条件を選んだ直後に開始通知を出す。CLIは番号と5条件を2列表で標準エラーに描画する。
4. 各試行の終了後、CLIは完了・枝刈り・失敗を表示し、完了なら暫定探索指標を表示する。最良試行を保存した後にその条件も表で示す。
5. 運用者が閾値と表示範囲を確認し`test --restart`を実行する。異常分割だけ入力画像の右に既存の重ね合わせ画像を連結し保存する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| checkpoint・探索履歴 | 形式変更なし | 既存契約 | 旧重みの成果物を再利用しない | 学習処理 | 全型番`train --restart` |
| 結果PNG | 変更 | 異常分割: 左右同じ高さのBGR画像 | 横幅は入力の2倍、正常分割は元サイズ | 検査処理 | `test --restart`で再生成 |
| `result_image`参照と結果JSON | 変更なし | 既存ファイル名とJSON項目 | 同名PNGを再生成 | 検査処理 | 形式互換 |
| 学習表示 | 追加 | 標準エラーの表と状態 | JSONは標準出力の一件だけ | CLI | 永続化しない。Optuna DBの履歴は既存どおり |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train --restart` | 運用者 → 学習CLI | 型番 | 新checkpoint、条件表 | 重み取得・学習失敗 → 既存失敗終了と試行状態 | 原因修正後に再実行 |
| 試行通知 | 探索 → CLI | 選択値と状態 | 標準エラーの表・結果 | 試行失敗・枝刈り → 状態表示、探索継続 | 該当なし |
| `test --restart` | 運用者 → 検査CLI | 型番 | 再生成した結果PNGとJSON | 個別分割失敗 → 既存のerror結果、正常画像を捏造しない | 原因修正後に再実行 |

## 技術判断

### 判断・候補: バックボーンと既存成果物

- **状態**: 確定。
- **採用内容**: 共有入口の固定名を`wide_resnet50_2.tv_in1k`へ変更し、全型番を明示的に再学習する。
- **根拠**: 利用者が性能を確認し、全型番の再学習を選択した。旧成果物の重み識別子を自動判定できない。
- **代替案**: 旧checkpointの継続利用は重みの出所を証明できないため採用しない。
- **実装規則 / 不変条件**: 前処理、スコア、探索候補、閾値契約を維持する。
- **影響**: モデル生成、テスト、README、仕様と再学習運用。

### 判断・候補: 異常結果画像

- **状態**: 確定。
- **採用内容**: 既存の`_heatmap`による重ね合わせ画像を作り、元画像と水平方向に連結して同じ結果パスへ保存する。
- **根拠**: 元画像を失わずに既存の異常表示と直接比較でき、JSON契約を変更しない。
- **代替案**: 別ファイル保存は参照契約を増やすため採用しない。
- **実装規則 / 不変条件**: 左右同じ画素寸法。正常分割は入力画素と同一。判定とヒートマップ色は不変。
- **影響**: `evaluation.py`、結果画像の横幅と保存容量。

### 判断・候補: 試行表

- **状態**: 確定。
- **採用内容**: 探索へ任意の開始・終了コールバックを追加し、学習CLIがRichの2列表を標準エラーへ表示する。非端末でも同じ項目を読める文字表を出す。
- **根拠**: 選択値が確定する探索境界から通知でき、探索の最適化ロジックを表示から分離できる。Richは既存依存である。
- **代替案**: Optunaの既定ログだけでは開始時の全条件と日本語の状態がまとまらない。
- **実装規則 / 不変条件**: 失敗・枝刈りは終了コールバックで状態を表示し、完了試行だけ指標を表示する。既存履歴の試行を再表示しない。標準出力JSON一件と終了コードを維持する。
- **影響**: `search.py`、学習CLI、関連テスト。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 試行が枝刈り・失敗 | Optuna | 既存の状態を保存 | 試行番号と状態を表示 | study.db | 残り試行を継続 |
| すべての試行が失敗 | 探索 | 最良成果物を保存しない | 既存の失敗終了 | 実行記録 | 原因修正後に再実行 |
| 分割画像の読込・保存失敗 | 検査 | 当該分割をerrorにする | 結果JSONに理由 | 結果JSON | 原因修正後に`test --restart` |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| セキュリティ | 新しい入力や外部送信を追加しない | 既存の安全なパスと結果契約を維持 |
| 性能 | 横連結は異常分割だけに適用し、推論回数は変えない | 対象環境で結果画像と実行時間を確認 |
| 運用 | 全型番の再学習と再検査をREADMEに記す | 旧成果物と混用しないことを確認 |

## 移行とロールバック

1. 旧探索履歴、checkpoint、型番設定、検査結果が必要なら版更新前に一式を退避する。
2. 全型番で`train --restart`を実行し、暫定閾値、`inspection_threshold`、`heatmap_range`を確認する。
3. 全型番で`test --restart`を実行し、新しい横結合画像と結果JSONを確認する。
4. ロールバック時は旧コード、旧設定、旧探索履歴、checkpoint、検査結果を一式で戻す。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-020 | REQ-020-S01 | integration | モデル生成を捕捉 | `tv_in1k`と事前学習指定 | `tests/test_training.py::test_model_adapter_uses_tv_backbone` | はい | 実ライブラリ、重み取得なし | 対象OSの実学習 (5.1) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-002 | REQ-020 | REQ-020-S02 | integration | 旧成果物で再学習開始 | 旧探索とcheckpointだけ削除 | `tests/test_training.py::test_training_restart_replaces_only_derived_artifacts` | はい | ローカル成果物 | 全型番の運用確認 (5.2) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-003 | REQ-010 | REQ-010-S01 | integration | 正常分割を検査 | 入力画像と画素一致 | `tests/test_evaluation.py::test_evaluation_records_normal_split` | はい | 固定画像 | 対象OSの実画像 (5.3) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-004 | REQ-010 | REQ-010-S02 | integration | 異常分割を検査 | 左が原画像、右が重ね合わせ、横幅2倍 | `tests/test_evaluation.py::test_evaluation_visualizes_anomalous_split` | はい | 固定画像 | 対象OSの実画像 (5.3) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-005 | REQ-010 | REQ-010-S03 | integration | 既存前処理付きモデルで推論 | 同じ決定的前処理 | `tests/test_evaluation.py::test_predictor_uses_model_preprocessor` | はい | モデル前処理 | 対象OSの実学習 (5.1) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-006 | REQ-010 | REQ-010-S04 | unit | 同値・範囲外の異常マップ | 色尺度と判定が不変 | `tests/test_evaluation.py::test_heatmap_uses_shared_range_across_images` | はい | 固定画素 | 対象OSの実画像 (5.3) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-007 | NREQ-004 | NREQ-004-S01 | integration | 試行開始を通知 | 5条件の表と開始概要 | `tests/test_training.py::test_search_reports_trial_conditions` | はい | 軽量runner、CLI表示 | 対象OS端末 (5.4) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-008 | NREQ-004 | NREQ-004-S02 | integration | 完了・枝刈り・失敗 | 状態と完了指標、JSON維持 | `tests/test_training.py::test_search_reports_trial_outcomes` | はい | 軽量runner、CLI表示 | 対象OS端末 (5.4) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |
| TC-009 | NREQ-004 | NREQ-004-S03 | integration | 既存履歴から再開 | 今回の試行数だけ表を表示 | `tests/test_training.py::test_search_reports_resumed_trial_count` | はい | Optuna履歴 | 対象OS端末 (5.4) | `openspec/changes/archive/2026-10-08-restore-tv-backbone-and-improve-output/evidence/implementation.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-020 | 2 | 2 | なし | 網羅 |
| REQ-010 | 4 | 4 | なし | 網羅 |
| NREQ-004 | 3 | 3 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 対象OSと実重みの学習・checkpoint検査 | TC-001と実学習・検査 | 実機実行 (5.1) | 未検証 | 未作成 |
| AC-002 | 対象の全型番と既存成果物 | TC-002、README確認、全型番の再実行 | 運用実施 (5.2) | 未検証 | 未作成 |
| AC-003 | 正常・異常の実画像 | TC-003, TC-004, TC-006と画像目視 | 対象OS実画像 (5.3) | 未検証 | 未作成 |
| AC-004 | 端末・非端末の試行表示とJSON | TC-007〜TC-009、対象OSのCLI確認 | 対象OS端末 (5.4) | 未検証 | 未作成 |
