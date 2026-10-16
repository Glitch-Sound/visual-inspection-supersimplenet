## 背景・前提

`trainer.py` の試行処理は `synthetic_auroc` のときseedを設定した後に `torch.use_deterministic_algorithms(True)` を呼び、復元しない。<br />
`cli.py` は探索後に必要な交差検証と全件再学習を行う。<br />
`artifacts.py` は `training_percentile` の閾値を試行の `training_scores` から計算し、別の最終checkpointを公開する。<br />
既存の成果物トランザクションと型番別・グループ別の契約を維持する。

## 目標・対象外

### 目標

- GPUで対応しない決定論演算により試行を失敗させず、例外時にも設定を元へ戻す。
- 従来方式の閾値を最終checkpointの全正常学習画像スコアから計算する。
- 最良試行結果で閾値スコアのモデル系統を識別し、3成果物の整合を守る。

### 対象外

- 学習対象外交差検証のスコアと閾値計算式の変更。
- GPUでのビット単位の再現性保証。非決定的CUDA演算が残るため。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-038 | 処理フロー、技術判断、境界条件と失敗モード | 試行・GPU状態 | 1.1、1.2、3.1 | TC-001〜TC-003 | 設定復元のpytest、CPU再現、CUDA実機 |
| REQ-007 | データ契約と状態、インターフェースと失敗時の結果 | スコア・成果物・検査読戻し | 2.1〜2.3、3.2 | TC-004〜TC-009 | pytestでスコアと3成果物を比較 |
| REQ-035 | 処理フロー、移行とロールバック | 全件再学習・最終checkpoint | 2.1、2.2、3.2 | TC-010〜TC-012 | pytestで画像集合とモデル由来を確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 試行学習 | 変更 | 目的、seed、デバイス | スコア、checkpoint、復元済み決定論状態 | Anomalib、PyTorch | `model_training/trainer.py` に確定。学習中の設定をここで閉じる |
| 全件再学習と評価 | 変更 | 最良条件、全正常分割画像 | 最終checkpointと評価スコア | Anomalib | `model_training/trainer.py` と `cli.py` に確定 |
| 閾値・成果物公開 | 変更 | 最終評価スコアまたは交差検証スコア | 同一閾値のcheckpoint・設定・JSON | 既存トランザクション | `model_training/artifacts.py` に確定 |
| 保存形式・検査読戻し | 変更 | 閾値モデル識別情報 | 妥当性確認済み結果 | 共通契約 | `common/contracts.py`、`model_evaluation/evaluation.py` に確定 |

### 処理フロー

1. `train` が設定と準備manifestを検証し、探索分割および全正常学習画像を取得する。
2. `synthetic_auroc` の各試行ではseedを固定し、開始前の決定論設定を記録する。<br />
CUDA非対応演算で中断しない設定にして学習・評価し、成功・失敗の両方で元の設定に戻す。
3. 新方式の交差検証は既存どおり各分割で実施する。<br />
従来方式には交差検証を追加しない。
4. 最良条件で全正常学習画像を学習し、専用の最終checkpointを保存する。<br />
従来方式ではこのモデルを評価モード、学習拡張なしで同じ全正常分割画像へ再適用し、返った `pred_score` の件数と有限性を検証する。
5. 従来方式は最終評価スコアの設定済みパーセンタイル、新方式は既存の学習対象外スコアとマージンから閾値を計算する。<br />
旧成果物を維持したまま計算・検証し、完成時だけ既存トランザクションで3成果物を公開する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 最良試行結果 | 追加 | `threshold_score_model: Literal["final_checkpoint", "cross_validation"]` | 新規結果では必須。従来方式は `final_checkpoint`、新方式は `cross_validation` | 成果物公開 | 旧結果はフィールドなしで読めるが、新方式の根拠を推測して補完しない |
| 最良試行結果 | 追加 | `threshold_model_checkpoint: str \| None` | 従来方式では `checkpoint` と同じ相対パス、新方式では `null` | 成果物公開 | 旧結果は未記録として扱う |
| 試行結果 | 維持 | `training_scores: list[float]` | 探索の記録には残すが従来閾値には使わない | 探索 | 保存済み履歴の再開を維持 |
| 公開済み3成果物 | 維持 | 暫定閾値: 0以上1以下の有限値 | checkpoint、型番設定、最良試行結果で一致 | 成果物公開 | 従来方式の再学習で値が変わり得る |

`threshold_score_model` は閾値に使ったスコアのモデル系統を表す。<br />
旧JSONは読戻しを維持するが、旧閾値を最終checkpoint由来と誤表示しない。<br />
新規結果では方式とモデル系統の組合せを契約で検証する。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train` | 運用者 → 学習 | 型番、グループ、再開始指定 | 閾値と成果物の実行記録 | 学習・スコア失敗 → 段階と理由を表示し旧一式を保持 | 原因修正後に再実行。方式変更時は `--restart` |
| 最終モデル評価 | 学習 → Anomalib | 全正常分割画像、最終モデル | 画像数と一致する有限なスコア | 欠落・件数不一致・非有限値 → 公開前に拒否 | 入力・環境修正後に再実行 |
| 結果の読戻し | 検査 → 共有契約 | JSON、checkpoint、設定 | 整合するモデルと閾値 | 新規結果の方式・モデル系統不一致 → 推論前に拒否 | 再学習または成果物の復旧 |

## 技術判断

### 判断・候補: GPU決定論設定の範囲

- **状態**: 確定
- **採用内容 / 候補**: `synthetic_auroc` の試行ではseedを固定し、PyTorchの決定論モードを試行範囲だけ無効にする。開始前の有効状態と `warn_only` 状態を保存し、`finally` で復元する。既に有効な外部設定も終了後に維持する。
- **根拠**: ユーザーが挙げたCUDA演算で決定論モードがエラーになる。GPUの厳密決定性は要件ではなく、seed固定とCPUの再現性が要件である。
- **代替案**: `warn_only=True` を試行範囲で有効にする案は警告が増える。決定論モードをプロセス全体で有効にする案は後続処理へ漏れる。
- **実装規則 / 不変条件**: 設定は `try/finally` で戻し、シード設定を試行ごとに行う。CUDAのビット同一性を宣言しない。
- **影響**: `trainer.py` の試行境界と設定復元テスト。

### 判断・候補: 最終checkpointのスコア取得

- **状態**: 確定
- **採用内容 / 候補**: `fit_selected_parameters` が最終学習後、保存したのと同じモデルを評価モードで学習拡張なしの全正常画像へ推論する。`cli.py` は返されたスコアを従来方式だけ `persist_best_trial` へ渡す。
- **根拠**: 最終checkpointと閾値算出モデルを一致させ、追加のモデル生成・重み読込みによる差を避ける。
- **代替案**: 試行の学習スコアは別モデル由来。公開後checkpointの読戻しによる再推論は公開中の旧一式との混在が起こり得る。
- **実装規則 / 不変条件**: checkpoint保存後に同一モデルで評価し、画像件数と全スコアの有限性・範囲を公開前に確認する。評価用入力には学習拡張を適用しない。
- **影響**: 従来方式の全件再推論時間が加わる。

### 判断・候補: 閾値根拠と一式公開

- **状態**: 確定
- **採用内容 / 候補**: 最良試行結果にモデル系統と、従来方式でのみ最終checkpoint参照を保存する。既存の3成果物トランザクションを使う。
- **根拠**: `checkpoint` 参照のみでは旧結果の閾値がどのモデル由来か分からない。
- **代替案**: `checkpoint` を閾値算出元と見なす方式は旧結果を誤読する。
- **実装規則 / 不変条件**: 新方式のスコアと閾値計算は変更しない。新規結果の方式・系統・参照の整合を検証する。
- **影響**: 共通契約、成果物公開、検査読戻し、既存JSONの互換処理。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 試行学習の例外 | 試行境界 | 決定論設定を復元。旧一式は不変 | 失敗した試行の理由 | 既存の試行・実行記録 | 原因修正後に再実行 |
| 最終評価の欠落・件数不一致・非有限スコア | 最終評価・公開 | 閾値を公開せず旧一式を保持 | 評価失敗と理由 | stderr、実行記録 | 入力または環境を修正して再実行 |
| 3成果物の書込み中断 | 公開 | 旧一式へ復旧 | 失敗した段階と理由 | 既存トランザクション記録 | 次の学習・検査で復旧 |
| 旧JSONのモデル系統欠落 | 読戻し | 旧契約として扱う | 新しい根拠として表示しない | 読戻し結果 | 対象グループを再学習 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力・機密 | 既存のmanifestと型番設定の検証を維持し、画像・秘密情報を証跡に埋め込まない | 不正入力は公開前に拒否 |
| 性能 | 従来方式は最終モデルで全正常分割画像を一回追加推論する | 対象環境で実行時間を記録。運用上限は本変更で定めない |
| 運用 | GPUの学習完了、CPU同seed再現、3成果物の読戻しを分けて確認する | OS、GPU、Python・依存版、seed、結果を証跡に記録 |

## 移行とロールバック

1. 既存の従来方式成果物は旧閾値のまま読めるが、最終モデル由来の閾値として扱わない。<br />
対象グループの旧成果物を必要なら退避し、`train --restart` で新しい成果物を作り、`test` で結果を再生成する。
2. 新方式の既存閾値計算は変更せず、再学習時も交差検証スコアを使う。
3. 失敗時は旧3成果物を維持する。変更を戻す場合は退避した旧成果物一式と対応設定を戻し、検査結果を再生成する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-038 | REQ-038-S01 | integration | CUDA相当の試行、交差検証、全件学習 | 試行中の非決定論設定と完了後の復元 | `tests/test_training.py::test_synthetic_trial_scopes_determinism` | はい | 状態契約のテストダブル | 実CUDA、3.3 | 未作成 |
| TC-002 | REQ-038 | REQ-038-S02 | unit | 試行で例外注入し次処理実行 | 設定復元と旧成果物保持 | `tests/test_training.py::test_synthetic_trial_restores_determinism_on_failure` | はい | 例外時状態 | 実CUDA、3.3 | 未作成 |
| TC-003 | REQ-038 | REQ-038-S03 | integration | CPU同seedで探索を2回 | 条件・目的値・最良試行一致 | `tests/test_training.py::test_synthetic_search_repeats_with_seed_on_cpu` | はい | CPU同環境 | 対象OS、3.4 | 未作成 |
| TC-004 | REQ-007 | REQ-007-S01 | integration | 従来・新方式の保存 | 3閾値一致とモデル系統 | `tests/test_training.py::test_final_artifact_threshold_contract` | はい | 保存契約 | 実モデル、3.3 | 未作成 |
| TC-005 | REQ-007 | REQ-007-S02 | integration | キャッシュの有無 | 再取得有無 | `tests/test_training.py::test_training_reuses_pretrained_cache` | はい | 既存試験 | 実機取得、3.3 | 未作成 |
| TC-006 | REQ-007 | REQ-007-S03 | integration | 更新中断 | 旧3成果物復旧 | `tests/test_training.py::test_refit_artifact_transaction_recovers` | はい | 既存試験 | 実機中断、3.3 | 未作成 |
| TC-007 | REQ-007 | REQ-007-S04 | integration | モデル系統と参照の不一致 | 推論前拒否 | `tests/test_training.py::test_threshold_model_mismatch_rejected` | はい | 読戻し契約 | 実機読戻し、3.3 | 未作成 |
| TC-008 | REQ-007 | REQ-007-S05 | integration | 2グループで学習 | 閾値独立 | `tests/test_training.py::test_refit_group_thresholds_are_independent` | はい | 既存試験 | 実機読戻し、3.3 | 未作成 |
| TC-009 | REQ-007 | REQ-007-S08 | integration | 最終スコア欠落・非有限値 | 理由と旧一式保持 | `tests/test_training.py::test_final_scores_invalid_preserve_artifacts` | はい | 公開前検証 | 実機エラー、3.3 | 未作成 |
| TC-010 | REQ-035 | REQ-035-S01 | integration | 新方式で学習 | 全件モデルとOOF閾値 | `tests/test_training.py::test_oof_final_refit_uses_all_sources` | はい | 既存試験 | 実重み、3.3 | 未作成 |
| TC-011 | REQ-035 | REQ-035-S02 | integration | 従来方式で学習 | 最終モデルの全件スコア百分位 | `tests/test_training.py::test_training_percentile_uses_final_checkpoint_scores` | はい | 計算とモデル由来 | 実重み、3.3 | 未作成 |
| TC-012 | REQ-035 | REQ-035-S03 | integration | 全件学習の失敗 | 理由と旧一式保持 | `tests/test_training.py::test_refit_failure_preserves_artifacts` | はい | 既存試験 | 実機失敗、3.3 | 未作成 |
| TC-013 | REQ-007 | REQ-007-S06 | integration | AUROC 1.0の試行が複数 | 上限到達件数と警告 | `tests/test_training.py::test_synthetic_auroc_ceiling_warning` | はい | 既存試験 | 対象OSでの読戻し | `openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md` |
| TC-014 | REQ-007 | REQ-007-S07 | unit | 上限未到達と旧結果 | 0と未記録を区別 | `tests/test_training.py::test_synthetic_ceiling_zero_and_legacy` | はい | 既存試験 | 対象OSでの読戻し | `openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md` |

証跡には自動試験のコマンド・結果と、実機のOS・GPU・Python・依存版・seed・結果を分けて記録する。<br />
テストダブルだけでCUDA演算の実行結果を確認済みとはしない。

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-038 | 3 | 3 | なし | 設計上網羅 |
| REQ-007 | 8 | 8 | なし | 設計上網羅 |
| REQ-035 | 3 | 3 | なし | 設計上網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | CUDAで `synthetic_auroc` の探索・交差検証・最終学習 | TC-001・TC-002、対象GPUで `train` | 実CUDAの一連実行、3.3 | 未検証 | 未作成 |
| AC-002 | CPU同seed・同入力・同環境で2回探索 | TC-003、対象OSで2回比較 | 対象OSでの再現、3.4 | 未検証 | 未作成 |
| AC-003 | 従来方式の最終モデル・全正常画像・評価スコア | TC-011、実checkpointで再計算 | 実重みでの再計算、3.3 | 未検証 | 未作成 |
| AC-004 | 3成果物の閾値とモデル識別情報 | TC-004・TC-007、対象OSで読戻し | 対象OSでの読戻し、3.3 | 未検証 | 未作成 |
| AC-005 | 不正スコア・学習失敗と旧一式保全 | TC-002・TC-006・TC-009・TC-012 | 対象環境での失敗・再実行、3.3 | 未検証 | 未作成 |
| AC-006 | 新方式の交差検証スコアと閾値の不変性 | TC-004・TC-010、既存回帰試験 | 実重みでの再確認、3.3 | 未検証 | 未作成 |
