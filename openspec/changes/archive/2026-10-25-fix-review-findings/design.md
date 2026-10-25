## 背景・前提

`common/config.py` が型番設定と準備指紋、`model_training/artifacts.py` が最良試行と checkpoint、`common/result_index.py` が検査結果の公開、`common/cli.py` が5コマンド共通の実行入口を担う。<br />
現在、結果公開は `common/atomic.py` の退避付き経路を使い、学習の探索履歴はストレージ接続が生きたまま移される。<br />
本変更は `src/app/<capability>/` の責務境界を保ち、共通の型番単位の処理だけを `common/` に置く。

## 目標・対象外

### 目標

- 設定省略、学習成果物、結果公開、エラー、再実行を差分仕様どおりに一致させる。
- 対象型番の管理対象一時領域を5コマンドの開始時に掃除する。
- 変更を再現する自動テストと追跡できる検証記録を用意する。

### 対象外

- 旧成果物の読取り互換、移行、退避からの復旧。
- 学習アルゴリズム、異常スコア、性能目標の変更。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-021 | 設定・一時領域・処理フロー | image-preparation / 共通CLI | 1.1, 6.1 | TC-001, TC-002, TC-003, TC-004, TC-005 | pytestで入力・表示・保存状態を照合 |
| REQ-027 | 設定・一時領域・処理フロー | image-preparation / 共通CLI | 1.1, 6.1 | TC-006, TC-007, TC-008 | pytestで入力・表示・保存状態を照合 |
| REQ-037 | 設定・一時領域・処理フロー | image-preparation / 共通CLI | 4.1, 6.1 | TC-009, TC-010 | pytestで入力・表示・保存状態を照合 |
| REQ-007 | 学習公開・処理フロー | model-training / 共通CLI | 2.1, 6.1 | TC-011, TC-012, TC-013, TC-014, TC-015, TC-016 | pytestで入力・表示・保存状態を照合 |
| REQ-008 | 学習公開・処理フロー | model-training / 共通CLI | 2.2, 6.1 | TC-017, TC-018, TC-019 | pytestで入力・表示・保存状態を照合 |
| REQ-034 | 学習公開・処理フロー | model-training / 共通CLI | 1.2, 6.1 | TC-020, TC-021, TC-022 | pytestで入力・表示・保存状態を照合 |
| REQ-038 | 学習公開・処理フロー | model-training / 共通CLI | 2.2, 6.1 | TC-023 | pytestで入力・表示・保存状態を照合 |
| REQ-013 | 検査照合・公開・処理フロー | model-evaluation / 共通CLI | 3.1, 6.1 | TC-024, TC-025, TC-026, TC-027, TC-028, TC-029, TC-030, TC-031, TC-032, TC-033, TC-034 | pytestで入力・表示・保存状態を照合 |
| REQ-016 | 検査照合・公開・処理フロー | model-evaluation / 共通CLI | 3.2, 6.1 | TC-035, TC-036, TC-037, TC-038, TC-039, TC-040 | pytestで入力・表示・保存状態を照合 |
| REQ-028 | 検査照合・公開・処理フロー | model-evaluation / 共通CLI | 3.1, 6.1 | TC-041, TC-042 | pytestで入力・表示・保存状態を照合 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 設定検証 | 変更 | 型番設定 | 補正の有効状態、入力不備 | 各 CLI | `common/config.py` に確定。5 CLI 共通の読込みだから |
| 一時領域の整理 | 追加 | 型番、管理対象パス | 前回の一時領域の削除 | 共通CLI、成果物パス | `common/cli.py` から呼ぶ共通処理に確定。ロック取得後、設定読込み前 |
| 学習成果物の公開 | 変更 | 最良試行、設定、checkpoint | 両成果物の擬似異常値と完了した探索履歴 | Optuna、ファイル保存 | `model_training/cli.py` と `artifacts.py` に確定 |
| 検査契約照合 | 変更 | 設定、最良試行、checkpoint | 不一致の拒否と再実行案内 | 推論前 | `model_evaluation/evaluation.py` に確定 |
| 検査結果の公開 | 変更 | 完成済み一時結果 | グループ結果の削除と移動 | ファイル保存 | `common/result_index.py` に確定 |

### 処理フロー

1. 共通CLIは型番を検証し、型番ロックを取得して、`data/03_check`、`data/04_train`、`data/05_test`、`data/06_result`、`optuna`、`weights` のうち当該型番に属する既知パターンの一時領域を全グループ分掃除する。候補がリンクや予想外の種類なら拒否する。
2. 設定読込みは `brightness_normalization` のキー全体がなければ `enabled=false` とする。キーがあれば既存の子項目既定値を使う。旧項目は明示的な「廃止された項目」で拒否し、巨大整数は有限数検査の失敗として入力不備にする。
3. `train` は探索を実行し、最良試行を確定した後、Optuna の RDB ストレージ接続を明示的に閉じる。次に暫定閾値と擬似異常設定の全既定値適用後の範囲を checkpoint と `best_trial.json` に保存して公開する。
4. `test` は対象グループごとに設定・最良試行・checkpoint の閾値と擬似異常設定値を推論前に照合する。欠落や不一致は `train` からの再実行を案内する。全対象の新結果を一時領域で完成させた後、各旧グループ結果を削除して新結果を移す。
5. 結果公開途中の失敗では当該グループが欠ける場合がある。旧結果の復旧は行わず、次の `test` は新しい結果を作る。全件実行で新旧の混在を解消する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番設定 | 変更 | `brightness_normalization` オブジェクト、省略可 | 全体省略時は補正無効。記述時は `enabled=true` ほか既定値を維持 | 運用者 / 設定読込み | 旧準備結果は再作成 |
| `best_trial.json` | 追加 | `synthetic_anomaly`、3範囲の `min`・`max`、必須 | グループの既定値適用後の設定値 | 学習 | 旧ファイルは非互換 |
| checkpoint `visual_inspection` | 追加 | `synthetic_anomaly`、同じ構造、必須 | 最良試行と一致 | 学習 | 旧checkpointは非互換 |
| 検査結果 | 変更 | `group_<ID>/` | 公開後は新結果一式。公開途中は欠落し得る | 検査 | 旧結果の退避・移行なし |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 5 CLI 開始 | 運用者 → 共通CLI | 型番 | 前回の管理対象一時領域を整理 | 危険なパス → 入力不備、他の領域を保護 | 同型番ロック内で再実行可 |
| 設定読込み | CLI → 設定 | JSON | 補正状態と学習条件 | 旧項目・巨大整数 → 入力不備 | 修正後に再実行 |
| 学習公開 | `train` → 成果物 | 探索結果 | 読み戻せる履歴と両成果物 | 保存失敗 → エラー、欠落・不整合は次回 `train` | 同型番で再学習 |
| 検査照合 | `test` → 学習成果物 | 3者の契約 | 推論開始 | 閾値未設定・不一致 → `train` 案内、結果は未公開 | 学習と試験準備後に再実行 |
| 結果公開 | `test` → 結果保存 | 完成済み一時結果 | 新結果一式 | 公開中断 → グループ欠落の可能性を表示 | `test` 再実行。全件で混在解消 |

## 技術判断

### 判断・候補: 一時領域の整理位置

- **状態**: 確定。
- **採用内容 / 候補**: 共通CLIが型番ロック取得直後に掃除する。
- **根拠**: 5コマンドと全グループを同じ条件で扱え、並走中の同型番の領域を消さない。
- **代替案**: 各成果物生成時の掃除は、別グループ・別工程の残骸が残るため採用しない。
- **実装規則 / 不変条件**: 既知の一時名と種類だけを対象とし、リンクは辿らず拒否する。管理対象外と別型番に触れない。
- **影響**: 共通CLI、既存の個別掃除処理、パス検証。

### 判断・候補: Optuna 接続終了と公開順

- **状態**: 確定。
- **採用内容 / 候補**: `create_study` で `RDBStorage` を明示的に生成して呼び出し元でも保持する。最良試行・履歴の必要値を読み取ってから、その `remove_session()` で接続を閉じ、`study.db` を含む一時領域を移す。ロック版の Optuna に `RDBStorage.remove_session()` があることを確認済み。
- **根拠**: SQLite ファイルを使用中の接続が移動後の履歴を保持しないようにする。
- **代替案**: プロセス終了まで待つ方法では Windows でファイル移動に失敗し得る。
- **実装規則 / 不変条件**: 接続終了後に `study` を再参照しない。必要な値は終了前に確保する。失敗時も終了処理を試みる。
- **影響**: 学習CLIと保存処理、Optuna 統合テスト。

### 判断・候補: 検査結果の公開

- **状態**: 確定。
- **採用内容 / 候補**: `result_index.py` で旧グループを検証後に削除し、完成済み一時グループを移す。退避処理と `recover_results` を削除する。
- **根拠**: 指定された公開契約と再実行手順に一致する。
- **代替案**: 退避付き公開は復旧状態を残し、要求に反する。
- **実装規則 / 不変条件**: 全対象の作成失敗では旧結果を保持。公開途中は欠落を許容し、次回は復旧せず再検査する。
- **影響**: 結果保存、テスト、README、正式仕様。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 一時領域候補がリンク | 共通CLI | 削除せず停止 | パスを示す入力不備 | 実行記録JSON | パスを点検して再実行 |
| 擬似異常に巨大整数 | 設定 | 成果物を更新せず停止 | 項目名を示す入力不備 | 実行記録JSON | 設定修正 |
| 暫定閾値が未設定 | 検査 | 推論・公開前に停止 | `train` 案内 | 実行記録JSON | 学習から再実行 |
| 最良試行・checkpoint・設定が不一致 | 検査 | 推論・公開前に停止 | 不一致とやり直し案内 | 実行記録JSON | 準備・学習・検査を再実行 |
| 結果公開途中で中断 | 検査 | 対象結果が欠け得る | エラー、次の `test` 案内 | 実行記録JSON | 全件 `test` |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| パス安全性 | 型番内の既知パターンのみ削除し、リンクを拒否 | 別型番・管理外・リンク先の不変をテストで確認 |
| 性能 | 開始時に型番の管理対象一時領域だけ列挙する | 既存の性能目標は変更しない。対象環境のスモークで実行時間を記録 |
| 運用 | 全工程再実行と公開中断時の `test` 再実行を README に明記 | 5 CLI の終了コードと成果物の読み戻しを確認 |

## 移行とロールバック

1. 旧成果物は移行しない。適用後は `check`、`train-pre`、`train`、`test-pre`、全件 `test` の順に実行する。
2. 公開途中の失敗では旧結果の復旧をしない。設定と成果物を確認して `test` を再実行する。
3. 旧版へ戻す場合も新旧成果物の互換性は前提にせず、旧版で全工程を再実行する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-021 | REQ-021-S01 | unit / integration | 運用者が型番のコマンドを実行する | 両グループが有効として扱われ、同じ分割IDにグループごとに異なる検査値を指定できる | `tests/test_config.py::test_group_req_021_s01` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-002 | REQ-021 | REQ-021-S02 | unit / integration | 運用者が check、train-pre、train、test-pre、test のいずれかを実行する | システムは対象グループID、判明している分割IDまたは要素位置、理由を示して入力不備として終了する | `tests/test_config.py::test_group_req_021_s02` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-003 | REQ-021 | REQ-021-S03 | unit / integration | 運用者が型番のコマンドを実行する | 必須グループがない理由を示して入力不備として終了し、暗黙のグループを作成しない | `tests/test_config.py::test_group_req_021_s03` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-004 | REQ-021 | REQ-021-S04 | unit / integration | 運用者が型番のコマンドを実行する | 不一致を示して入力不備として終了し、既存成果物を更新しない | `tests/test_config.py::test_group_detail_rejects_mismatched_ids` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-005 | REQ-021 | REQ-021-S05 | unit / integration | 運用者が型番のコマンドを実行する | グループID、項目名と、旧項目については「廃止された項目」を示して入力不備として終了し、既存成果物を更新しない | `tests/test_config.py::test_per_range_rejects_group_legacy_fields` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-006 | REQ-027 | REQ-027-S01 | unit / integration | 運用者が当該型番の train-pre または test-pre を実行する | 子項目には既定値が適用され、補正が有効な準備結果を取得できる | `tests/test_config.py::test_brightness_defaults` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-007 | REQ-027 | REQ-027-S03 | unit / integration | 運用者が train-pre または test-pre を実行する | 分割画像は輝度補正を受けず、準備指紋も無効状態を示す | `tests/test_config.py::test_brightness_defaults` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-008 | REQ-027 | REQ-027-S02 | unit / integration | 運用者が当該型番のコマンドを実行する | 不正な項目を示す入力不備として処理開始前に終了し、元画像と既存の準備成果物を変更しない | `tests/test_config.py::test_brightness_rejects_invalid_settings` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-009 | REQ-037 | REQ-037-S01 | unit / integration | 運用者がその型番のいずれかのコマンドを開始する | 対象型番の管理対象一時領域がすべて消え、別型番と管理対象外は残る | `tests/test_config.py::test_all_commands_clear_model_stages` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-010 | REQ-037 | REQ-037-S02 | unit / integration | 運用者がその型番のコマンドを開始する | 対象パスを示して拒否し、リンク先と管理対象外を変更しない | `tests/test_config.py::test_model_stage_symlink_is_rejected` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-011 | REQ-007 | REQ-007-S01 | unit / integration | 学習処理が完了する | 型番・グループ別のcheckpointと最良試行結果に同じ暫定閾値、スコア契約、対応情報が保存される | `tests/test_training.py::test_group_req_007_s01` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-012 | REQ-007 | REQ-007-S02 | unit / integration | 運用者が学習を実行する | 保存済みの重みを利用し、同じ重みを再ダウンロードしない | `tests/test_model_adapter.py::test_group_req_007_s02` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-013 | REQ-007 | REQ-007-S03 | unit / integration | 新成果物の作成途中で失敗または中断する | 旧学習成果物と型番設定は変更されず、失敗理由が示される | `tests/test_training.py::test_group_req_007_s03` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-014 | REQ-007 | REQ-007-S04 | unit / integration | 運用者が検査を実行する | 不一致項目を示してモデル生成・推論前に拒否し、再学習を促す | `tests/test_training.py::test_group_req_007_s04` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-015 | REQ-007 | REQ-007-S05 | unit / integration | 運用者が両グループの学習を実行する | 各グループのcheckpoint、最良試行結果、設定にグループ別の暫定閾値が整合して保存される | `tests/test_training.py::test_group_req_007_s05` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-016 | REQ-007 | REQ-007-S06 | unit / integration | 運用者がそのグループの train を完了する | 適用された全範囲が checkpoint のメタデータと best_trial.json の両方に同じ値で記録される | `tests/test_training.py::test_group_req_007_s01` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-017 | REQ-008 | REQ-008-S02 | unit / integration | 運用者が train --model <型番> --group <ID> を実行する | 既存探索履歴を使わず新規の探索と学習を行い、全処理の成功後に対象グループの探索結果とモデルを置き換える | `tests/test_training.py::test_group_req_008_s02` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-018 | REQ-008 | REQ-008-S03 | unit / integration | 運用者が train --model <型番> を実行する | コマンドは失敗グループIDと理由を示してエラー終了する | `tests/test_training.py::test_group_req_008_s03` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-019 | REQ-008 | REQ-008-S04 | unit / integration | 運用者が train を再実行する | 対象型番の管理対象一時領域をグループを問わず削除し、旧探索履歴を再開せず最初から探索する | `tests/test_training.py::test_req_008_s04` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-020 | REQ-034 | REQ-034-S01 | unit / integration | 運用者が学習を開始する | 入力不備の理由が示され、探索と学習成果物の更新は始まらない | `tests/test_config.py::test_synthetic_anomaly_rejects_invalid_bounds` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-021 | REQ-034 | REQ-034-S02 | unit / integration | 運用者が学習を開始する | 入力不備として拒否され、既存の学習成果物は更新されない | `tests/test_config.py::test_synthetic_anomaly_rejects_invalid_types` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-022 | REQ-034 | REQ-034-S03 | unit / integration | 運用者が型番のコマンドを実行する | 入力不備として項目を示し、未処理例外では終了しない | `tests/test_config.py::test_synthetic_anomaly_huge_integer_is_input_error` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-023 | REQ-038 | REQ-038-S01 | unit / integration | 運用者が保存された探索履歴を読み戻す | 最良試行を含む完了済み履歴を参照できる | `tests/test_training.py::test_closed_storage_history_reads_from_published_path` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-024 | REQ-013 | REQ-013-S01 | unit / integration | 運用者が test --model <型番> を実行する | 全対象グループの新結果が完成するまで旧結果を保持し、完成後は各対象グループに最新結果一式だけを残す | `tests/test_evaluation.py::test_result_replace_after_all_groups_complete` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-025 | REQ-013 | REQ-013-S02 | unit / integration | 運用者が test --model <型番> --group <ID> を実行する | 指定グループだけを新結果へ置き換え、他グループの結果を変更しない | `tests/test_evaluation.py::test_result_single_group_preserves_others` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-026 | REQ-013 | REQ-013-S03 | unit / integration | 全対象グループの新結果が完成する前に失敗または中断する | 対象グループの旧結果をすべて保持し、一時結果を整理して失敗グループIDと理由を表示する | `tests/test_evaluation.py::test_result_stage_failure_preserves_all_groups` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-027 | REQ-013 | REQ-013-S04 | unit / integration | 運用者が次の test を実行する | 旧結果の復旧を行わず、新たな検査結果を作成して公開する | `tests/test_evaluation.py::test_result_recreates_missing_group_after_publish_interrupt` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-028 | REQ-013 | REQ-013-S05 | unit / integration | 運用者が検査を開始する | システムは不正なパスを示して拒否し、リンク先や管理外のファイルを読み書き・削除しない | `tests/test_evaluation.py::test_result_rejects_symlink_paths` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-029 | REQ-013 | REQ-013-S07 | unit / integration | 運用者が全グループの test を実行する | 全対象グループの結果を完成させた後に各グループを公開する | `tests/test_evaluation.py::test_result_replace_after_all_groups_complete` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-030 | REQ-013 | REQ-013-S08 | unit / integration | 運用者が train-pre、train、test-pre のいずれかを実行する | 検査結果だけを理由に処理を拒否しない | `tests/test_evaluation.py::test_result_residue_does_not_block_preparation` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-031 | REQ-013 | REQ-013-S09 | unit / integration | 運用者が全グループの test を正常に実行する | 設定にあるグループの新結果を公開し、設定にないグループ結果だけを削除する | `tests/test_evaluation.py::test_result_full_run_removes_unconfigured_groups` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-032 | REQ-013 | REQ-013-S10 | unit / integration | 運用者が次の test を実行する | システムは対象型番の管理対象一時領域を整理してから新しい検査を開始する | `tests/test_evaluation.py::test_result_stale_stage_removed` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-033 | REQ-013 | REQ-013-S11 | unit / integration | 運用者が全グループの test を実行する | 失敗グループIDと理由を示してエラー終了する | `tests/test_evaluation.py::test_result_full_run_failure_preserves_all` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-034 | REQ-013 | REQ-013-S12 | unit / integration | 運用者が次の test を実行する | 残った一時結果を削除して新しい結果を作り、公開まで対象グループの旧結果を保持する | `tests/test_evaluation.py::test_result_stale_stage_removed` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-035 | REQ-016 | REQ-016-S01 | unit / integration | 運用者が test --model <型番> を実行する | 契約照合を通過し、分割画像の検査が実行される | `tests/test_evaluation.py::test_group_req_016_s01` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-036 | REQ-016 | REQ-016-S02 | unit / integration | 運用者が test --model <型番> を実行する | 必要なメタデータがない理由を示して検査開始前にエラー終了する | `tests/test_evaluation.py::test_group_req_016_s02` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-037 | REQ-016 | REQ-016-S03 | unit / integration | 運用者がそのグループの検査を実行する | グループ不一致を示して推論前に拒否し、既存の結果を保持する | `tests/test_evaluation.py::test_group_req_016_s03` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-038 | REQ-016 | REQ-016-S04 | unit / integration | 運用者が検査を実行する | 不一致を示して推論前に拒否し、train からのやり直しを促す | `tests/test_evaluation.py::test_mismatched_training_artifacts_require_train` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-039 | REQ-016 | REQ-016-S05 | unit / integration | 運用者が検査を実行する | 閾値の不一致を示して推論前に拒否し、train からのやり直しを促す | `tests/test_evaluation.py::test_mismatched_training_artifacts_require_train` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-040 | REQ-016 | REQ-016-S06 | unit / integration | 運用者が検査を実行する | train の実行が必要と案内して推論前に拒否する | `tests/test_evaluation.py::test_mismatched_training_artifacts_require_train` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-041 | REQ-028 | REQ-028-S01 | unit / integration | 運用者が検査を実行する | 各グループの結果は group_00、group_09、group_10、group_100 の直下に元画像別JSONと分割結果画像だけを持つ | `tests/test_group_artifact_names.py::test_result_group_names` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |
| TC-042 | REQ-028 | REQ-028-S02 | unit / integration | 運用者が検査を再実行する | 対象グループの保存先には今回作成したJSONと画像だけが残る | `tests/test_evaluation.py::test_result_rerun_drops_old_source_files` | はい | ローカルの契約・保存状態 | 対象OSの一連の実行 (6.3) | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-021 | 5 | 5 | なし | 設計済み |
| REQ-027 | 3 | 3 | なし | 設計済み |
| REQ-037 | 2 | 2 | なし | 設計済み |
| REQ-007 | 6 | 6 | なし | 設計済み |
| REQ-008 | 3 | 3 | なし | 設計済み |
| REQ-034 | 3 | 3 | なし | 設計済み |
| REQ-038 | 1 | 1 | なし | 設計済み |
| REQ-013 | 11 | 11 | なし | 設計済み |
| REQ-016 | 6 | 6 | なし | 設計済み |
| REQ-028 | 2 | 2 | なし | 設計済み |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | ローカル、設定省略と明記時の準備画素・指紋 | `pytest tests/test_config.py tests/test_preparation.py` | 対象OSでの一連の確認 (6.3) | 未検証 | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |
| AC-002 | ローカル、最良試行とcheckpointの記録値 | `pytest tests/test_training.py` | 対象OSでの読戻し (6.3) | 未検証 | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |
| AC-003 | ローカル、公開前・公開途中・再実行の結果状態 | `pytest tests/test_evaluation.py` | 対象OSでの再実行 (6.3) | 未検証 | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |
| AC-004 | ローカル、接続終了と探索履歴読戻し | `pytest tests/test_training.py` | Windows 11でのファイル移動 (6.3) | 未検証 | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |
| AC-005 | ローカル、5 CLIと全グループの残存物 | `pytest tests/test_preparation.py tests/test_training.py tests/test_evaluation.py` | 対象OSでの確認 (6.3) | 未検証 | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |
| AC-006 | ローカル、入力不備と案内 | `pytest tests/test_config.py tests/test_evaluation.py` | なし | 検証済み | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |
| AC-007 | ローカル、二種類の混在と結果未公開 | `pytest tests/test_evaluation.py` | 対象OSでの成果物読戻し (6.3) | 未検証 | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |
| AC-008 | README・正式仕様の指定文言と新契約 | 文書レビュー、`openspec validate` | なし | 検証済み | `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` |

## 試験例外

なし。文言のみの変更は既存Scenarioの題名であり、実装変更の受け入れ試験に含めてレビューする。
