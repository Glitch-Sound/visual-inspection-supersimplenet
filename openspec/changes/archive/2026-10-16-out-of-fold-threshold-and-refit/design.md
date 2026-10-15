## 背景・前提

現行の `src/app/model_training/cli.py` は準備manifestから一つの元画像単位分割を作り、`search.py` でOptuna探索し、`artifacts.py` が最良試行の学習スコアから閾値を算出して試行checkpointを公開する。<br />
`trainer.py` は分離済み画像をAnomalibへ渡し、推論結果の `pred_score` を取得する。<br />
`common/config.py` はグループ別 `threshold.method` を `training_percentile` に限定し、`common/contracts.py` の `BestTrialResult` は探索分割だけを記録する。<br />
準備manifestはブラックリスト適用後のグループ別画像を表す。<br />
探索用の固定分割、既存の型番排他と学習成果物一式の復旧境界を維持する。

## 目標・対象外

### 目標

- グループ別設定で閾値方式、分割、パーセンタイル、マージンを検証する。
- 全対象元画像を一度ずつ検証し、学習対象外スコアの出所を追跡できる。
- 最良条件で全対象画像を再学習し、整合するcheckpoint・設定・結果を一式公開する。

### 対象外

- 探索試行数、目的関数、探索分割の変更。
- 実異常画像の性能評価と本番用閾値の決定。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-033 | 業務フローと責務、技術判断 | 設定・元画像分割・学習 | 1.1、2.1、2.2 | TC-001〜TC-003 | pytestの分割集合・呼出し確認、対象OS読戻し |
| REQ-034 | データ契約と状態、技術判断 | スコア・閾値・結果 | 1.1、2.3、3.1 | TC-004、TC-005 | pytestの数値・結果JSON確認、対象OS読戻し |
| REQ-035 | 処理フロー、移行とロールバック | 最終学習・checkpoint公開 | 2.4、3.1 | TC-006〜TC-008 | pytestの全件投入・失敗保全、対象OS検査 |
| REQ-007 | データ契約と状態、インターフェースと失敗時の結果 | 成果物一式・検査読戻し | 3.1、3.2 | TC-009〜TC-013 | pytestの保存・復旧・整合・独立性 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| グループ設定 | 変更 | `threshold` と準備manifest | 検証済みの閾値条件 | 既存設定読込 | `common/config.py` に確定。複数能力で共有する契約 |
| 元画像分割 | 追加 | manifest、分割条件、seed | 非重複の学習・検証集合 | 準備済み画像 | `model_training/search.py` に確定。探索用分割と同じ元画像解決を利用 |
| 学習・推論 | 変更 | 最良条件、画像集合 | 交差検証スコア、最終checkpoint | Anomalib | `model_training/trainer.py` に確定。学習責務に閉じる |
| 統合・公開 | 変更 | スコア、checkpoint、探索結果 | 閾値と結果JSON、公開済み成果物一式 | `common/artifact_transaction.py` | `model_training/cli.py` と `artifacts.py` に確定。既存一式更新を利用 |
| 読戻し契約 | 変更 | 最良試行結果JSON | 検証済み契約 | 検査 | `common/contracts.py` に確定。共有保存形式 |

### 処理フロー

1. `train` は型番設定と準備manifestを検証し、ブラックリスト除外後の元画像を列挙する。<br />
新方式の分割数は探索・公開済み成果物への変更前に検証する。
2. 探索は既存の固定分割と目的関数で実行する。<br />
再開済みの最良試行も含め、最良条件を読み戻す。
3. 新方式では最良条件で各交差検証分割を独立して学習し、その分割の検証画像をeval推論する。<br />
元画像名・分割画像名とスコアを対応させ、全件被覆・非重複・有限値を確認する。<br />
従来方式では最良試行の学習スコアを使用する。
4. 算出した閾値を確認した後、最良条件で全対象正常画像を再学習する。<br />
最終checkpointは専用の一時領域で作り、探索・交差検証checkpointを公開しない。
5. 既存の成果物トランザクションでcheckpoint、型番設定、最良試行結果を一式更新する。<br />
失敗時は旧一式を復旧し、運用者は同じ `train` を再実行する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| グループ閾値設定 | 変更 | `method: training_percentile \| out_of_fold_percentile`、`percentile: float`、`margin: float`、`folds: int \| leave_one_out` | 従来方式が既定。百分位は(0,100]、マージンは[0,1]。新方式のみ分割指定を要する | 運用者、設定検証 | 既存設定は従来方式として読める |
| 最良試行結果 | 変更 | `threshold_method`、`final_train_sources: list[str]`、新方式時 `cross_validation: list[fold]`、`score_by_source: list[source/split/score]`、`threshold_percentile`、`threshold_margin` | 元画像・分割画像名は安全なbasename、一意。全件被覆。スコアは有限の[0,1] | 学習完了時 | 旧結果は従来方式として読める。新方式の証跡は補完しない |
| checkpointメタデータ | 維持 | 型番、グループ、スコア契約、閾値 | 設定と最良試行結果に一致 | 成果物公開 | 既存検査の読戻し契約を維持 |

設定の `folds` は新方式で整数2以上または文字列 `leave_one_out` とし、分割画像別スコアにより元画像ごとの根拠を失わない。<br />
マージン0は新方式の既定とする。<br />
閾値は `min(1, percentile(scores, p) + margin)` とし、スコア集合を元画像単位へ集約してから百分位を取る処理は行わない。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train` | 運用者 → 学習 | 型番、グループ、`--restart` | 1件の実行記録JSON、閾値とcheckpoint | 不正設定・元画像不足 → 終了コード2と理由 | 設定修正後に再実行。探索履歴は既存規則で再開 |
| 学習・推論 | 学習 → Anomalib | 最良条件、集合 | スコア、最終checkpoint | 欠落・非有限スコア、実行失敗 → 終了コード3と段階・理由 | 公開済み一式を維持して再実行 |
| 一式公開 | 学習 → ファイル | checkpoint、設定、JSON | 同一閾値の3成果物 | 中断・書込み失敗 → 次コマンド前に旧一式へ復旧 | 既存トランザクションを利用 |
| `test` 読戻し | 検査 → 保存契約 | 3成果物 | 最終checkpointで推論 | 閾値・契約不一致 → 推論前に拒否 | 成果物を復旧または再学習 |

## 技術判断

### 判断・候補: 交差検証と探索の分離

- **状態**: 確定
- **採用内容 / 候補**: 探索は現行の一分割を維持し、最良条件だけを全分割に適用する。固定seedで元画像を並べて分割し、1枚ずつ方式は元画像数を分割数とする。
- **根拠**: 探索試行ごとの交差検証を避ける利用者要件。既存の分割と評価目的を維持できる。
- **代替案**: 各試行を交差検証する方式は学習回数が大幅に増え、今回の範囲外。
- **実装規則 / 不変条件**: 各元画像は一度だけ検証、同一元画像の分割画像は同側。探索結果は交差検証で再選択しない。
- **影響**: 新方式は探索後に分割数回の学習を追加する。

### 判断・候補: 最終学習と成果物公開

- **状態**: 確定
- **採用内容 / 候補**: 最終学習を探索・交差検証とは独立に全件で行い、既存の3成果物トランザクションで公開する。
- **根拠**: 全件学習と旧一式保全を同時に満たす。
- **代替案**: 最良試行checkpointの再利用は8割学習のまま残る。
- **実装規則 / 不変条件**: 全件学習のcheckpointだけを公開する。閾値は最終モデルの学習スコアから再算出しない。
- **影響**: 従来方式を含め探索後に1回の学習が増える。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 元画像不足・不正な分割条件 | 設定・分割 | 公開済み成果物は不変 | 必要数と現在数を表示 | stderrと実行記録 | 設定・データ修正後に再実行 |
| 欠落・非有限・件数不一致のスコア | 学習・スコア収集 | 公開済み成果物は不変 | 分割と理由を表示 | stderrと実行記録 | 原因修正後に再実行 |
| 最終学習・保存の失敗 | 学習・公開 | 既存一式を維持または復旧 | 段階と理由を表示 | stderrと復旧記録 | 同じコマンドを再実行 |
| 再開時の条件変更 | 探索・公開 | 異なる条件の再開を拒否 | `train --restart` を案内 | stderrと実行記録 | 対象グループを再探索 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力安全性 | manifestと元画像名の既存検証を使用し、新しい結果JSONも安全なbasenameだけを許可 | 不正パスの拒否と既存成果物の保持 |
| 性能 | 新方式は探索後に分割数回、両方式とも全件学習1回を追加 | CLIで段階・分割番号を表示し、実機の経過時間を記録。運用上限は本changeでは未設定 |
| 運用 | 新方式での再学習と検査結果の再生成を案内 | 対象OSで設定・結果・checkpointを読戻す |

## 移行とロールバック

1. 既存設定は `training_percentile` のまま読める。新方式の設定値を入れる時は対象グループの探索履歴との条件整合を確認し、必要なら `train --restart` を使う。
2. 既存checkpointは新方式の交差検証証跡を持たないため、新方式へ切り替えるグループを再学習する。検査結果も再生成する。
3. 学習失敗時は公開済み一式を維持する。変更を戻す場合は従来方式の設定で再学習し、検査結果を再生成する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-033 | REQ-033-S01 | unit | 5元画像、3分割で構築 | 非重複・全件被覆、探索値不変 | `tests/test_training.py::test_oof_folds_cover_sources_without_leakage` | はい | 分割と探索契約 | 実機読戻し、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-002 | REQ-033 | REQ-033-S02 | unit | 3元画像で1枚ずつ | 3分割、検証各1枚 | `tests/test_training.py::test_leave_one_out_uses_each_source_once` | はい | 分割境界 | 実機読戻し、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-003 | REQ-033 | REQ-033-S03 | unit | 1元画像、不正分割数 | 拒否と旧成果物保持 | `tests/test_training.py::test_oof_rejects_invalid_fold_count` | はい | 設定・入力 | 実機エラー、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-004 | REQ-034 | REQ-034-S01 | unit / integration | 既知のOOFスコアで学習 | 百分位・加算・上限、JSONの対応 | `tests/test_training.py::test_oof_threshold_and_score_provenance` | はい | テストダブルと保存形式 | 実モデル、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-005 | REQ-034 | REQ-034-S02 | integration | 欠落・非有限スコアを注入 | 理由と旧一式保持 | `tests/test_training.py::test_oof_invalid_scores_preserve_artifacts` | はい | 学習境界 | 実機エラー、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-006 | REQ-035 | REQ-035-S01 | integration | 新方式で学習 | 全件投入、最終重みの参照 | `tests/test_training.py::test_oof_final_refit_uses_all_sources` | はい | テストダブル | 実重み検査、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-007 | REQ-035 | REQ-035-S02 | integration | 従来方式で学習 | 旧閾値、全件checkpoint | `tests/test_training.py::test_legacy_threshold_with_full_refit` | はい | 従来互換 | 実重み検査、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-008 | REQ-035 | REQ-035-S03 | integration | 最終学習失敗を注入 | 段階表示と旧一式保持 | `tests/test_training.py::test_refit_failure_preserves_artifacts` | はい | 失敗契約 | 実機失敗、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-009 | REQ-007 | REQ-007-S01 | integration | 2方式の保存 | 3閾値一致、全記録 | `tests/test_training.py::test_final_artifact_threshold_contract` | はい | 保存形式 | 実機読戻し、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-010 | REQ-007 | REQ-007-S02 | integration | 重みキャッシュ有無 | 再取得有無 | `tests/test_training.py::test_training_reuses_pretrained_cache` | はい | テストダブル | 実機取得、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-011 | REQ-007 | REQ-007-S03 | integration | 更新中断を注入 | 旧一式復旧 | `tests/test_training.py::test_refit_artifact_transaction_recovers` | はい | ファイル復旧 | 実機中断、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-012 | REQ-007 | REQ-007-S04 | integration | 不整合結果で検査 | 推論前拒否 | `tests/test_training.py::test_refit_contract_mismatch_rejected` | はい | 読戻し境界 | 実機読戻し、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| TC-013 | REQ-007 | REQ-007-S05 | integration | 2グループで学習 | 閾値独立 | `tests/test_training.py::test_refit_group_thresholds_are_independent` | はい | グループ境界 | 実機読戻し、4.2 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |

TC-001〜TC-013のpytestは自動試験の証跡に記録する。<br />
テストダブルによる契約確認は、実ライブラリを使う全CLI・対象OS確認を代替しない。<br />
証跡にはコマンド、日付、OS、Python・依存版、使用デバイス、結果、制約を記録する。

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-033 | 3 | 3 | なし | 設計上網羅 |
| REQ-034 | 2 | 2 | なし | 設計上網羅 |
| REQ-035 | 3 | 3 | なし | 設計上網羅 |
| REQ-007 | 5 | 5 | なし | 設計上網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 指定分割数・1枚ずつ、元画像非重複 | TC-001〜TC-003、対象OSで結果読戻し | 対象OSでの実画像・結果読戻し、4.2 | 未検証 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| AC-002 | 実スコア、百分位、マージン、記録 | TC-004・TC-005、対象OSで再計算 | 対象OSでの実スコア再計算、4.2 | 未検証 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| AC-003 | 全件学習と最終checkpointの検査 | TC-006、対象OSの実重み検査 | 対象OSでの実重み・checkpoint検査、4.2 | 未検証 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| AC-004 | 従来方式の閾値と全件学習 | TC-007、対象OSで読戻し | 対象OSでの従来方式・全件学習読戻し、4.2 | 未検証 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| AC-005 | 3成果物一致、不正入力・失敗・復旧 | TC-003・TC-005・TC-008〜TC-013、起動時復旧試験 | 対象OSでの失敗・中断・復旧、4.2 | 未検証 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
| AC-006 | Ubuntu 24.04 LTS・Windows 11の実画像とCPU/GPU | 対象OSで `train`、`test`、成果物読戻し | 対象OSでの一連の実機確認、4.2 | 未検証 | `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/automated.md` |
