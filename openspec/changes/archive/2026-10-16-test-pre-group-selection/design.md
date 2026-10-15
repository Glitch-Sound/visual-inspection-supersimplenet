## 背景・前提

`test-pre` は `src/app/image_preparation/cli.py` から `prepare_testing` を呼び、型番共通の `data/05_test/<model>/` をディレクトリ単位で置き換える。<br />
`test` は同じ領域のmanifestを読み、グループの分割IDだけを検査する。<br />
準備指紋は型番共通の分割・位置合わせ条件を表す。
単独準備で位置合わせに失敗すると旧分割が保持されるため、検査側で最新の位置合わせ状態を確認する。

## 目標・対象外

### 目標

- `--group` 指定時だけ対象分割を作り直し、既存の対象外分割を保持する。
- manifestと画像を一式として置き換え、失敗時は既存一式を維持する。
- 引数省略時は従来の全件準備を保つ。
- 最新の位置合わせが失敗した元画像では、保持された旧分割を推論に使わず未判定へ引き継ぐ。

### 対象外

- グループ別試験準備領域とmanifest形式の変更。
- 元画像の更新履歴管理。<br />
既存の対象外分割は以前の準備結果を引き継ぐため、元画像や準備条件を大きく変えた場合は全件再準備する。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-003 | 処理フロー、データ契約と状態、インターフェースと失敗時の結果 | CLI選択、準備結果の統合と置換 | 1.1、1.2、2.1、3.1 | TC-001〜TC-010 | `tests/test_preparation.py` のpytestとCLIの終了記録 |
| REQ-011 | 処理フロー、データ契約と状態、技術判断 | 検査で最新の位置合わせ状態を確認する境界 | 2.2、3.6 | TC-011、TC-012、TC-013、TC-014、TC-015 | 集約単体試験と保持旧分割を伴う検査結合試験 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| CLIの選択 | 変更 | 任意の整数 `--group` | 対象IDの記録 | 型番設定 | `image_preparation/cli.py` に確定 |
| 試験準備 | 変更 | 設定、元画像、対象グループ | 分割画像と型番共通manifest | 共通契約・保存先 | `image_preparation/preparation.py` に確定 |
| 検査判定 | 変更 | 準備manifest、グループ分割 | 元画像・グループ別判定 | 共通契約・保存先 | `model_evaluation/evaluation.py` に確定 |

### 処理フロー

1. CLIで設定を読み、存在するグループIDを選択する。<br />
省略時は全分割を対象とする。
2. 単独指定で既存成果物がある場合、manifestの型番と準備指紋を確認する。<br />
異なる条件の成果物は混在させず、全件再準備を案内する。
3. 一時領域に既存の対象外分割画像を複写し、今回の全試験元画像を位置合わせして対象分割を生成する。<br />
既存manifestの同名元画像から対象外分割記録を引き継ぎ、削除された元画像の記録は引き継がない。
4. 対象グループの分割記録は今回の結果へ置き換える。<br />
位置合わせ失敗時は対象分割を作らず、未判定と再撮影要否を記録する。
5. manifestと画像を一時領域ごと置き換える。<br />
失敗時は一時領域を破棄し、既存成果物を保持する。
6. 検査では元画像の最新の位置合わせ状態を確認し、失敗なら保持された旧分割を推論せず、未判定と再撮影要否を記録する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 試験manifest | 形式変更なし | `group=null`、`sources`、`preparation_fingerprint` | 対象外分割を統合し、分割画像名は重複しない | `prepare_testing` | 従来形式をそのまま読む |
| 分割画像 | 部分更新 | 元画像名と分割IDで識別 | 対象分割を更新し、対象外の既存分割を保持 | `prepare_testing` | 保存先は従来どおり |
| 検査結果 | 判定条件を追加 | `overall_status`、`alignment`、`next_action` | 位置合わせ失敗なら旧分割があっても `undetermined` | `evaluate_model` | 結果形式は従来どおり |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `test-pre` | 運用者 → CLI | `--model`、任意の `--group` | 対象グループと準備結果を記録 | 不明ID・旧指紋 → 入力不備、既存保持 | 修正または全件準備で再実行 |
| 分割処理 | CLI → 準備 | 元画像と設定 | 一式を置換 | 読込み・分割失敗 → 処理失敗、既存保持 | 元画像を修正して再実行 |
| 検査 | 運用者 → 評価 | 共通manifestと対象グループ | 正常・異常・未判定結果 | 最新の位置合わせ失敗 → 旧分割を使わず未判定 | 再撮影後に全件準備または対象グループ準備 |

## 技術判断

### 判断・候補: 共通の試験準備領域を部分更新する

- **状態**: 確定。
- **採用内容 / 候補**: 既存manifestと画像を一時領域で統合し、成功時にディレクトリごと置換する。
- **根拠**: `test` が共通manifestを読む既存契約と、利用者が選んだ他分割保持の動作を満たす。
- **代替案**: グループ別保存先は `test` の読込み契約を変えるため採用しない。
- **実装規則 / 不変条件**: 既存の準備指紋不一致では統合しない。<br />
対象外の画像は存在確認してから複写し、対象分割の旧画像は複写しない。<br />
manifestと画像を別々に公開しない。
- **影響**: 部分更新後のmanifestには以前の対象外分割と今回の対象分割が共存する。

### 判断・候補: 位置合わせ失敗時の保持旧分割

- **状態**: 確定。
- **採用内容 / 候補**: 画像と準備記録は保持し、検査では位置合わせ失敗の元画像について分割推論を行わず未判定にする。
- **根拠**: 他グループの保存結果を保持しながら、旧画像を最新の正常判定に使用しない。
- **代替案**: 旧分割を削除すると他グループ成果物の保持契約を満たさない。<br />
旧分割を推論すると再撮影要否のある元画像が正常と判定され得る。
- **実装規則 / 不変条件**: 位置合わせ失敗の元画像ではpredictorを呼ばず、再撮影要否と失敗理由を結果に引き継ぐ。
- **影響**: 旧分割は残るが、再準備が成功するまでその元画像の検査判定に使わない。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 不明グループ | 設定選択 | 更新なし | 利用可能なIDを示す | CLI終了記録 | 正しいIDで再実行 |
| 準備指紋の不一致 | 既存manifest読込み | 更新なし | 全件準備を案内 | CLI終了記録 | `test-pre --model` |
| 読込み・分割失敗 | 準備処理 | 一時領域を破棄 | 対象画像と失敗を示す | CLI終了記録 | 元画像修正後に再実行 |
| 位置合わせ失敗と旧分割 | 検査判定 | 旧分割を使わず未判定 | 再撮影と再準備を示す | 検査結果JSONと警告 | 元画像を再撮影して準備を再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 既存設定のグループ選択とmanifest検証を使用 | 不明IDと異なる指紋を拒否 |
| 性能 | 対象外画像の複写は部分更新のために必要 | 数値目標は既存仕様にないため追加しない |
| 運用 | 元画像や共通条件を変更した場合は全件再準備を案内 | READMEの手順を確認 |

## 移行とロールバック

1. manifest形式と保存先を変更しないため移行は不要。<br />
旧動作へ戻す場合も `test-pre --model` で全件再準備できる。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-003 | REQ-003-S01 | integration | 全件準備 | 全分割を保存 | `tests/test_preparation.py::test_req_003_s01` | はい | ローカル画像処理 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-002 | REQ-003 | REQ-003-S02 | integration | 位置合わせ失敗 | 未判定と再撮影要否 | `tests/test_preparation.py::test_req_003_s02` | はい | テストダブル | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-003 | REQ-003 | REQ-003-S03 | integration | 範囲外 | エラー、成果物なし | `tests/test_preparation.py::test_req_003_s03` | はい | テストダブル | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-004 | REQ-003 | REQ-003-S04 | integration | 読込み不能 | 既存一式を保持 | `tests/test_preparation.py::test_req_003_s04` | はい | ローカルI/O | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-005 | REQ-003 | REQ-003-S05 | integration | similarity・replicate | 端画素を複製 | `tests/test_preparation.py::test_similarity_replicate_testing_pixels` | はい | 画像処理 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-006 | REQ-003 | REQ-003-S06 | integration | 変換推定失敗 | 未判定 | `tests/test_preparation.py::test_alignment_estimation_failure_undetermines_testing` | はい | テストダブル | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-007 | REQ-003 | REQ-003-S07 | integration | 共有分割を持つ複数グループ | 対象更新・他分割保持、単独検査成功 | `tests/test_evaluation.py::test_req_003_s07_evaluation` | はい | テストダブルとCLI・保存契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-008 | REQ-003 | REQ-003-S08 | integration | 既存なしで単独準備 | 対象分割だけ保存、単独検査成功 | `tests/test_evaluation.py::test_req_003_s08_evaluation` | はい | テストダブルとCLI・保存契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-009 | REQ-003 | REQ-003-S09 | integration | 不明ID | 入力不備・既存保持 | `tests/test_preparation.py::test_req_003_s09` | はい | CLIと保存契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-010 | REQ-003 | REQ-003-S10 | integration | 準備指紋不一致 | 入力不備・既存保持 | `tests/test_preparation.py::test_req_003_s10` | はい | CLIと保存契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-011 | REQ-011 | REQ-011-S01 | unit | 異常分割あり | 元画像を異常に集約 | `tests/test_results.py::test_group_req_011_s01` | はい | 集約契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-012 | REQ-011 | REQ-011-S02 | unit | 全分割正常 | 元画像を正常に集約 | `tests/test_results.py::test_group_req_011_s02` | はい | 集約契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-013 | REQ-011 | REQ-011-S03 | unit | 分割不足 | 未判定と次行動 | `tests/test_results.py::test_group_req_011_s03` | はい | 集約契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-014 | REQ-011 | REQ-011-S04 | integration | グループ別結果 | 別々に保存 | `tests/test_results.py::test_group_req_011_s04` | はい | 結果保存契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
| TC-015 | REQ-011 | REQ-011-S05 | integration | 位置合わせ失敗と保持旧分割 | 推論せず未判定と再撮影要否 | `tests/test_evaluation.py::test_req_011_s05_retained_splits_undetermined` | はい | テストダブルとCLI・結果契約 | 対象OS、3.3 | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-003 | 10 | 10 | なし | 網羅 |
| REQ-011 | 5 | 5 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | Ubuntu 24.04 LTS・Windows 11、複数グループと共有分割 | 実画像で単独準備と単独検査、他分割の比較 | 対象OS実機、3.3 | 未検証 | 未作成 |
| AC-002 | 両対象OS、全件準備、不明ID、画像読込み失敗 | CLI結果と準備領域の比較 | 対象OS実機、3.4 | 未検証 | 未作成 |
| AC-003 | 両対象OS、README手順、全グループ準備済み | 単独準備後に全件検査 | 対象OS実機、3.5 | 未検証 | 未作成 |
| AC-004 | macOSのテストダブルによる位置合わせ失敗、旧分割保持 | `npm run check` で旧分割未使用、未判定と再撮影要否を確認 | なし | 検証済み | openspec/changes/archive/2026-10-16-test-pre-group-selection/evidence/automated.md |
