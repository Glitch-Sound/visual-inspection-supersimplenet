## 背景・前提

現行の型番設定は `src/app/common/config.py` の `GroupConfig` がグループ単位の `range_ids`、`inspection_threshold`、`heatmap_range` を保持する。<br />
画像準備、学習、検査は `GroupConfig.range_ids` を参照し、準備指紋、manifest、最良試行、検査結果へ渡す。<br />
検査は `src/app/model_evaluation/evaluation.py` がグループ単位の閾値と表示範囲を選び、`src/app/model_evaluation/cli.py` が開始時に閾値を表示する。<br />
元画像別JSONの契約は `src/app/common/contracts.py` にある。<br />
現行の `test` は段階領域で全対象の結果を作成してから公開する。能力間は `common/` の明示契約を介して接続し、直接importを増やさない。

## 目標・対象外

### 目標

- 分割ごとに完全な検査条件を必須とし、5コマンド共通の設定読込み時に全グループを検証する。
- 分割条件から導いたIDを既存の内部 `range_ids` へ渡し、検査値を準備指紋から除く。
- 分割別の閾値・出どころ・表示範囲を判定、画像、開始表示、元画像別JSONに一貫して使う。

### 対象外

- 旧形式を読み替える互換層、旧成果物の移行、グループ単位の値による上書き。
- 暫定閾値の分割別学習、元画像判定集約規則の変更。
- 新しい外部サービス、権限方式、性能目標。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-021 | データ契約と状態、インターフェースと失敗時の結果 | 共通設定の検証 | 1.1、3.1 | TC-001〜TC-005 | 設定と5コマンドの拒否・旧成果物保全 |
| REQ-025 | データ契約と状態、移行とロールバック | 準備指紋・manifest | 1.2、3.2 | TC-006〜TC-009 | 指紋とmanifestの読戻し |
| REQ-029 | 処理フロー、データ契約と状態 | 学習の分割選択・閾値書戻し | 2.1、3.3 | TC-010〜TC-012 | 最良試行と設定差分 |
| REQ-010 | 処理フロー、技術判断 | 分割判定・画像 | 2.2、3.4 | TC-013〜TC-016 | 固定スコア・異常マップと保存画像 |
| REQ-012 | データ契約と状態、インターフェースと失敗時の結果 | 結果JSON | 2.3、3.5 | TC-017〜TC-022 | 結果契約・公開前拒否 |
| REQ-018 | 処理フロー、技術判断 | 分割閾値・暫定閾値照合 | 2.2、3.4 | TC-023〜TC-028 | 境界値・出どころ・照合 |
| REQ-019 | 処理フロー、技術判断 | 分割表示範囲 | 2.2、3.4 | TC-029、TC-030 | 異常画像と設定拒否 |
| REQ-036 | インターフェースと失敗時の結果 | 検査開始表示 | 2.4、3.5 | TC-031 | 標準エラーとJSONの一致 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 型番設定 | 変更 | `groups[].ranges[]`、`group_detail` | 検証済み `GroupConfig` または入力不備 | 5コマンド | `src/app/common/config.py` に確定。全コマンドが既存の設定読込みを使うため |
| 準備・学習対象 | 変更 | グループの分割ID | 準備指紋、manifest、最良試行 | 共通設定 | `image_preparation/preparation.py`、`model_training/cli.py` と `artifacts.py` に確定。既存のID利用箇所のため |
| 分割検査 | 変更 | 分割条件、推論値 | 判定、画像、分割結果 | 共通設定・結果契約 | `model_evaluation/evaluation.py` に確定。判定と画像の責務があるため |
| 結果・実行表示 | 変更 | 使用閾値と出どころ、表示範囲 | 元画像別JSON、標準エラー | 分割検査 | `common/contracts.py` と `model_evaluation/cli.py` に確定。保存形式とCLI表示の既存境界のため |

### 処理フロー

1. 5コマンドは共通設定を読み込む。全グループの分割条件と旧項目を検証し、不備なら段階領域の作成や成果物更新前に終了コード2で返す。
2. 画像準備は `ranges[].id` から対象分割IDを得る。学習準備の指紋とmanifestへIDを記録し、検査値は指紋へ含めない。試験準備は型番共通の全分割を準備する。
3. 学習は同じIDで対象を選び、最良試行の `range_ids` に記録する。グループ単位の暫定閾値だけを対象 `group_detail` に書き戻す。
4. 検査はcheckpoint・最良試行・設定の暫定閾値を照合し、分割条件ごとに使用閾値と出どころを確定して表示する。各分割を対応する閾値で判定し、異常画像を対応する表示範囲で色付けする。
5. 分割結果に使用値を記録し、既存の元画像集約と段階公開を行う。分割失敗・未判定でも使用予定値を結果へ記録する。設定値だけの変更は `test` を再実行する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番設定グループ | 変更 | `id`: 整数、`ranges`: 非空配列、各要素の `id`: 整数、`inspection_threshold`: 数値またはnull、`heatmap_range`: min/max数値。全て必須 | 分割IDはグループ内一意かつ共通 `range` に存在。閾値0～1の有限数、表示範囲は有限でmin<max。既定値・継承なし | 運用者・共通設定 | 旧3項目を拒否。全工程再実行 |
| 内部対象ID | 維持 | `range_ids`: 分割ID配列 | `groups[].ranges[].id` から導く。既存のmanifest・最良試行・指紋の名前は維持 | 共通設定と各能力 | 旧成果物との互換は扱わない |
| 準備指紋 | 変更 | 既存の文字列 | 学習用は分割IDを含む。閾値・表示範囲を含めない | 共通設定 | 新形式で再準備 |
| 元画像別JSON | 変更 | 各 `splits[]` に `threshold`: 0～1の有限数、`threshold_source`: `provisional`/`configured`、`heatmap_range`: 有限min/max。必須 | 推論エラー・未判定時も使用予定値を記録。グループ直下の旧2項目は拒否 | 分割検査・共通結果契約 | 旧結果を読み替えない |

## インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 設定読込み | 5コマンド → 共通設定 | 型番JSON | 全グループの検証済み条件 | 欠落・旧項目・不正値 → グループID、判明する分割IDまたは位置、理由、終了コード2。旧成果物不変 | 修正後に再実行 |
| 準備・学習 | CLI → 各能力 | 分割ID | 既存形式の内部 `range_ids` とグループ暫定閾値 | 準備指紋不一致・処理失敗 → 既存の拒否・段階公開規則 | 新形式の初回は全工程再実行 |
| 検査 | CLI → 評価能力 | 分割条件、checkpoint、試験準備 | 分割判定、画像、JSON、分割別開始表示 | 暫定閾値不一致・manifest不整合 → 推論前拒否。個別推論失敗 → error/undeterminedを記録 | 設定値だけなら `test` を再実行。旧結果公開は既存規則 |
| 結果読戻し | 評価者 → 元画像別JSON | グループ・元画像の結果 | 分割別の使用条件と判定 | 旧・不正契約 → 理由を示して拒否 | 新形式で結果再生成 |

## 技術判断

### 判断・候補: 設定モデルとIDの導出

- **状態**: 確定。
- **採用内容 / 候補**: `GroupConfig` は分割条件の配列を保持し、既存の呼び出し箇所へは導出した `range_ids` を提供する。入力時は必須キーを省略可能な既定値に変えず、旧グループ項目を拒否する。
- **根拠**: 値の出どころを一意にし、既存のmanifest・最良試行の内部記録を保てる。
- **代替案**: 旧グループ値からの継承は不採用。使用値が設定の複数箇所で決まるため。
- **実装規則 / 不変条件**: 全グループを選択前に検証する。`null` と欠落を区別する。エラー位置にはグループIDとIDまたは配列位置を含める。
- **影響**: 旧形式設定は必ず入力不備になる。

### 判断・候補: 検査値と内部記録の分離

- **状態**: 確定。
- **採用内容 / 候補**: 準備指紋は導出IDを使い、検査閾値・表示範囲を含めない。評価時に分割条件のIDから値を選択し、使用値・出どころ・範囲を一つの分割結果へ渡す。
- **根拠**: 準備画像の画素・所属は検査値に依存せず、結果の条件を分割単位で照合できる。
- **代替案**: 分割条件全体の指紋化は検査値だけの変更でも再準備を要求するため不採用。
- **実装規則 / 不変条件**: 同じ分割IDをグループ間で共有しても条件は混ぜない。暫定閾値は全分割で一つ。`pred_score >= threshold`。公開前失敗は旧結果保持。
- **影響**: 新結果JSONを読む側は分割結果の項目を参照する。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 分割条件の欠落・旧項目・重複・不正値 | 共通設定 | 成果物更新前に拒否 | グループ・分割・理由と終了コード2 | 既存標準エラーと実行記録 | 設定修正後に同じコマンドを再実行 |
| 暫定閾値または準備指紋の不一致 | 検査 | 推論・公開前に拒否、旧結果保持 | 不一致の対象と再学習・再準備の必要性 | 既存エラー記録 | 対象工程から再実行 |
| 個別分割の推論失敗・位置合わせ失敗 | 検査 | 使用予定条件を記録し、errorまたはundeterminedとして集約 | 元画像結果と理由 | 結果JSONと警告・エラー | 画像・条件を確認して再検査 |
| 結果作成中の後続グループ失敗 | 検査公開 | 全対象の旧結果保持 | 失敗グループIDと理由 | 既存実行記録 | 原因修正後に全件再検査 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 真偽値、非有限数、欠落、余分な旧項目を拒否する | TC-002、TC-005、TC-027、TC-030 |
| 性能 | 分割IDから条件を選択し、既存の分割処理回数を増やさない | 自動試験と対象OSの実行記録を確認。新しい数値目標は設けない |
| 運用 | 初回は全工程、検査値だけの変更は `test` を再実行する | AC-005、AC-006と対象OSの読戻し |

認証・認可と外部通知は現行のローカルCLIに存在せず、本変更で追加しない。

## 移行とロールバック

1. 型番設定を新形式へ書き換え、旧成果物を引き継がず `check` → `train-pre` → `train` → `test-pre` → `test` を実行する。新形式のmanifest、最良試行、結果JSONを読戻して完了を判定する。
2. 閾値・表示範囲だけを後から変えた場合は `test` のみ再実行する。分割IDや準備画像へ影響する設定の変更は従来どおり前段から再実行する。
3. ロールバックは旧コード・旧設定・対応する旧成果物一式へ戻す。混在利用しない。旧一式がなければ旧環境で再生成する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-021 | REQ-021-S01 | unit | 複数グループで同じIDに別値を設定して読込む | 両グループの値を保持 | `tests/test_config.py::test_per_range_shared_id_between_groups` | はい | 設定モデル | 対象OSの全CLI確認 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-002 | REQ-021 | REQ-021-S02 | integration | 欠落・重複・型・境界・未定義IDで5コマンドを実行 | 終了2、位置と理由、旧成果物不変 | `tests/test_config.py::test_per_range_invalid_config_all_commands` | はい | 共通読込みと5CLI | 対象OS確認 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-003 | REQ-021 | REQ-021-S03 | unit | groupsなしで設定読込み | 必須グループ不備 | `tests/test_config.py::test_group_req_021_s03` | はい | 設定モデル | 対象OS確認 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-004 | REQ-021 | REQ-021-S04 | unit | 詳細IDの欠落・余分・非標準表記 | 入力不備、旧成果物不変 | `tests/test_config.py::test_group_detail_rejects_mismatched_ids` | はい | 設定モデル | 対象OS確認 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-005 | REQ-021 | REQ-021-S05 | integration | 旧項目と詳細項目をgroupsに置いてCLI実行 | グループ・項目を示して拒否 | `tests/test_config.py::test_per_range_rejects_group_legacy_fields` | はい | 設定とCLI | 対象OS確認 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-006 | REQ-025 | REQ-025-S01 | integration | 新形式でtrain-pre | manifestのIDと指紋が一致 | `tests/test_preparation.py::test_group_req_025_s01` | はい | 学習準備とmanifest | 対象OSの実画像 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-007 | REQ-025 | REQ-025-S02 | integration | 新形式でtest-pre後にグループ条件を変更 | 試験指紋は不変 | `tests/test_config.py::test_per_range_testing_fingerprint` | はい | 試験指紋 | 対象OSの実画像 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-008 | REQ-025 | REQ-025-S03 | unit | 輝度補正条件を変更 | 両指紋が変化 | `tests/test_config.py::test_per_range_brightness_fingerprint` | はい | 準備指紋 | 対象OSの実画像 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-009 | REQ-025 | REQ-025-S04 | integration | 検査値のみ変えてtest再実行 | 準備・学習不変、新結果へ反映 | `tests/test_evaluation.py::test_per_range_values_change_without_repreparation` | はい | 指紋と検査 | 対象OSの実画像 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-010 | REQ-029 | REQ-029-S01 | integration | 複数グループの一方を学習 | 対象暫定値のみ書戻し、最良試行ID一致 | `tests/test_training.py::test_req_020_s02` | はい | 学習契約 | 対象OSの学習 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-011 | REQ-029 | REQ-029-S02 | integration | 詳細欠落でtrain | 設定不備と旧成果物保持 | `tests/test_training.py::test_per_range_training_rejects_missing_detail` | はい | 学習CLI | 対象OSの学習 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-012 | REQ-029 | REQ-029-S03 | integration | 書戻し失敗を注入 | 元設定保持、再検査拒否 | `tests/test_training.py::test_req_029_s03` | はい | 学習公開と設定 | 対象OSの学習 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-013 | REQ-010 | REQ-010-S01 | integration | スコアを分割閾値未満に固定 | normalと元画素の結果 | `tests/test_evaluation.py::test_group_req_010_s01` | はい | 予測ダブルと画像保存 | 実モデル・対象OS (5.2) | `evidence/implementation.md` (自動試験) |
| TC-014 | REQ-010 | REQ-010-S02 | integration | スコアを分割閾値以上に固定 | anomalyと分割別色付けの左右画像 | `tests/test_evaluation.py::test_group_req_010_s02` | はい | 予測ダブルと画像保存 | 実モデル・対象OS (5.2) | `evidence/implementation.md` (自動試験) |
| TC-015 | REQ-010 | REQ-010-S03 | integration | 学習・検査の前処理を照合 | 同じ決定的前処理、試験拡張なし | `tests/test_evaluation.py::test_group_req_010_s03` | はい | 前処理契約 | 実モデル・対象OS (5.2) | `evidence/implementation.md` (自動試験) |
| TC-016 | REQ-010 | REQ-010-S04 | unit | 異なるマップに同じ表示範囲を適用 | 同値同色・範囲外端色 | `tests/test_evaluation.py::test_group_req_010_s04` | はい | 画素計算 | 対象OS結果画像 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-017 | REQ-012 | REQ-012-S01 | integration | 正常・異常・未判定・エラーの結果を作成 | 各分割の使用条件、旧項目なし、集約一致 | `tests/test_results.py::test_per_range_result_contract` | はい | JSON契約と結果保存 | 対象OS読戻し (5.2) | `evidence/implementation.md` (自動試験) |
| TC-018 | REQ-012 | REQ-012-S02 | unit | 欠落・不正・旧項目のJSON読戻し | 理由を示して拒否 | `tests/test_results.py::test_per_range_rejects_invalid_result` | はい | 結果モデル | 対象OS読戻し (5.2) | `evidence/implementation.md` (自動試験) |
| TC-019 | REQ-012 | REQ-012-S03 | integration | 同stem異拡張子で検査 | JSONと画像は別名 | `tests/test_results.py::test_group_req_012_s03` | はい | 保存名 | 対象OS読戻し (5.2) | `evidence/implementation.md` (自動試験) |
| TC-020 | REQ-012 | REQ-012-S04 | integration | 不正manifestを検査へ渡す | 推論前拒否、旧結果不変 | `tests/test_results.py::test_group_req_012_s04` | はい | 入力境界 | 対象OS読戻し (5.2) | `evidence/implementation.md` (自動試験) |
| TC-021 | REQ-012 | REQ-012-S05 | integration | 同じIDを2グループで検査 | JSON分離、異なる値を保持 | `tests/test_evaluation.py::test_per_range_group_results_are_distinct` | はい | グループ結果 | 対象OS読戻し (5.2) | `evidence/implementation.md` (自動試験) |
| TC-022 | REQ-012 | REQ-012-S06 | integration | 分割位置変更後に旧試験準備で検査 | 指紋不一致、旧結果保持 | `tests/test_results.py::test_group_req_012_s06` | はい | 準備照合 | 対象OS読戻し (5.2) | `evidence/implementation.md` (自動試験) |
| TC-023 | REQ-018 | REQ-018-S01 | integration | 閾値キー欠落でtest | 必須項目不備、旧結果保持 | `tests/test_evaluation.py::test_per_range_missing_threshold` | はい | 設定と検査CLI | 対象OS検査 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-024 | REQ-018 | REQ-018-S02 | integration | nullでtest | 暫定値・provisional | `tests/test_evaluation.py::test_group_req_018_s02` | はい | 閾値選択 | 対象OS検査 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-025 | REQ-018 | REQ-018-S03 | integration | 指定閾値でtest | 指定値・configured、暫定値保持 | `tests/test_evaluation.py::test_group_req_018_s03` | はい | 閾値選択 | 対象OS検査 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-026 | REQ-018 | REQ-018-S04 | unit | 0・1とスコア一致で判定 | anomaly | `tests/test_evaluation.py::test_group_req_018_s04` | はい | 比較境界 | 対象OS検査 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-027 | REQ-018 | REQ-018-S05 | integration | 範囲外・非数値・非有限で5コマンド | 入力不備、旧成果物不変 | `tests/test_config.py::test_per_range_invalid_threshold_all_commands` | はい | 設定と5CLI | 対象OS検査 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-028 | REQ-018 | REQ-018-S06 | integration | 暫定値不一致でtest | 推論前拒否 | `tests/test_evaluation.py::test_group_req_018_s06` | はい | 学習成果物照合 | 対象OS検査 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-029 | REQ-019 | REQ-019-S01 | integration | 分割ごとの別範囲で検査 | 画像・JSON別値、スコア不変 | `tests/test_evaluation.py::test_per_range_group_results_are_distinct` | はい | 可視化と結果 | 対象OS画像 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-030 | REQ-019 | REQ-019-S02 | integration | 不正範囲で5コマンド | 入力不備、旧成果物不変 | `tests/test_config.py::test_per_range_invalid_heatmap_all_commands` | はい | 設定と5CLI | 対象OS確認 (5.2) | `evidence/implementation.md` (自動試験) |
| TC-031 | REQ-036 | REQ-036-S01 | integration | nullと指定値の混在でtest | 開始表示のID・値・出どころがJSONと一致 | `tests/test_evaluation.py::test_per_range_threshold_start_display` | はい | CLI標準エラーと結果 | 対象OS端末表示 (5.2) | `evidence/implementation.md` (自動試験) |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-021 | 5 | 5 | なし | 網羅 |
| REQ-025 | 4 | 4 | なし | 網羅 |
| REQ-029 | 3 | 3 | なし | 網羅 |
| REQ-010 | 4 | 4 | なし | 網羅 |
| REQ-012 | 6 | 6 | なし | 網羅 |
| REQ-018 | 6 | 6 | なし | 網羅 |
| REQ-019 | 2 | 2 | なし | 網羅 |
| REQ-036 | 1 | 1 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 複数グループ・同一IDの別条件、両対象OS | TC-001、TC-021と実機設定読戻し | 対象OS確認 (5.2) | 未検証 | `evidence/implementation.md` (自動試験) |
| AC-002 | 全不正条件と5コマンド、旧成果物保全、両対象OS | TC-002、TC-005、TC-027、TC-030とCLI終了状態確認 | 対象OS確認 (5.2) | 未検証 | `evidence/implementation.md` (自動試験) |
| AC-003 | 分割判定・境界・可視化・元画像集約、両対象OS | TC-013〜TC-016、TC-024〜TC-026、TC-029と実画像確認 | 対象OS画像確認 (5.2) | 未検証 | `evidence/implementation.md` (自動試験) |
| AC-004 | JSON・開始表示の一致、両対象OS | TC-017、TC-018、TC-031と保存JSON・端末表示照合 | 対象OS読戻し (5.2) | 未検証 | `evidence/implementation.md` (自動試験) |
| AC-005 | 値変更後のtest再実行、内部ID、両対象OS | TC-006〜TC-010と準備・学習成果物の差分照合 | 対象OSの再検査 (5.2) | 未検証 | `evidence/implementation.md` (自動試験) |
| AC-006 | 設定例、README、全工程再実行、両対象OS | 4.1と対象OSスモーク手順・成果物読戻し | 対象OS全工程 (5.2) | 未検証 | `evidence/implementation.md` (設定例・文書レビュー) |
