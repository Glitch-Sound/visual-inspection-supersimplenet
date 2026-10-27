## 背景・前提

試験準備は現在 `src/app/image_preparation/cli.py` と `preparation.py` が全分割を型番共通領域へ公開する。<br />
`model_evaluation` は共通領域のmanifestを照合する。学習準備は既にグループ別の段階公開を持つ。<br />
能力間の共有パス・manifest契約は `common/` に置く。

## 目標・対象外

### 目標

- 単独の `test-pre` と `test` が同じグループの準備を扱い、他グループを保持する。
- 全件では各グループの準備を作り、各グループの準備を検査前に照合する。

### 対象外

- 旧成果物の移行と互換層、学習・判定規則の変更。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-003 | 処理フロー、インターフェースと失敗時の結果 | 画像準備CLI・分割公開 | 1.1、2.1 | TC-001〜TC-007 | CLIと準備成果物 |
| REQ-025 | データ契約と状態 | 指紋とmanifest | 1.2、2.2 | TC-008〜TC-011 | 指紋・manifest読戻し |
| REQ-041 | 処理フロー、インターフェースと失敗時の結果 | 検査前照合と入力選択 | 1.3、2.3 | TC-012〜TC-014 | 検査結果と失敗時保全 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 試験準備CLI | 変更 | 型番、任意のID | 対象グループの記録 | 共通設定・準備処理 | `image_preparation/cli.py` に確定。既存入口 |
| 準備成果物 | 変更 | 元画像、対象分割 | グループ別画像とmanifest | 共通パス・契約 | `image_preparation/preparation.py` に確定。既存処理 |
| 検査 | 変更 | グループ別準備 | グループ別結果 | 共通パス・契約 | `model_evaluation/cli.py`、`evaluation.py` に確定。既存読戻し |

### 処理フロー

1. `test-pre` は設定全体を検証してから対象グループを選択する。未知IDは成果物を更新せず終了コード2とする。
2. 単独指定なら対象グループだけを一時領域で準備して公開する。省略時はID順で全グループを準備し、完成したグループから公開する。同じ元画像の位置合わせ結果は実行中に再利用する。
3. `test` は対象グループごとに準備manifestと設定・分割ID・指紋を照合し、そのグループの画像を検査する。欠落・不一致なら結果公開前にグループID付きで拒否する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 試験準備領域 | 変更 | `data/05_test/<model>/group_<ID>/` | IDは最低2桁で0埋め | 画像準備 | 旧共通領域は読まない |
| 試験manifest | 変更 | `group`: 整数、`range_ids`: 整数配列、`preparation_fingerprint`: 文字列 | 対象グループと完全一致 | 画像準備・共通契約 | 旧manifestは読まない |
| 試験指紋 | 変更 | 64桁ハッシュ | 型番共通の画像条件とグループID・分割IDを含み、ブラックリスト・検査値を除く | 共通設定 | 全再準備 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `test-pre` | 運用者 → 画像準備 | `--model`、任意の`--group` | 対象グループの画像・manifest、実行記録 | 未知ID→2、画像失敗→3。対象と理由を示す | 修正後に対象から再実行 |
| `test` | 運用者 → モデル評価 | 型番、任意のID | 対象グループ結果 | 準備欠落・不整合→対象IDと再準備を示し旧結果維持 | `test-pre` から再実行 |

## 技術判断

### 判断・候補: グループ別の試験準備

- **状態**: 確定。
- **採用内容 / 候補**: 学習準備と同様、試験準備をグループ別ディレクトリへ段階公開する。
- **根拠**: 単独実行で他グループを変更せず、分割の重複も独立して扱える。
- **代替案**: 型番共通領域の部分更新はmanifestと画像の原子的な一式公開が難しいため不採用。
- **実装規則 / 不変条件**: 全件ではID順。単独実行は対象ディレクトリのみ置換。試験指紋にブラックリストを入れない。学習指紋は既存のままとする。
- **影響**: 旧試験準備は利用できず、全工程の再実行を求める。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 未知ID | 共通設定 | 更新なし | 利用可能IDと終了コード2 | 実行記録 | IDを修正 |
| 位置合わせ不能 | 画像準備 | 未判定を保存 | 理由と再撮影要否 | manifest・警告 | 再撮影後に再準備 |
| 読込み・分割・公開前失敗 | 画像準備 | 対象旧成果物を保持 | グループIDと理由 | 実行記録 | 修正後に再実行 |
| 準備欠落・不整合 | モデル評価 | 旧結果を保持 | グループIDと再準備案内 | 実行記録 | 対象を再準備 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力・パス | 既存のID検証とシンボリックリンク拒否をグループ別領域へ適用 | TC-007、TC-014 |
| 性能 | 全件実行中の位置合わせ結果を元画像ごとに再利用 | 自動試験の呼出し回数。新しい数値目標はない |
| 運用 | 全工程を新形式で再実行 | 対象環境の実画像による読戻し |

認証・認可と外部連携はローカルCLIにないため対象外とする。

## 移行とロールバック

1. 旧成果物は引き継がず、`check`、`train-pre`、`train`、`test-pre`、`test` を順に全件再実行する。
2. 旧版へ戻す場合は旧版の形式で全工程を再実行する。結果を混在させない。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-003 | REQ-003-S01 | integration | 2グループで単独準備 | 対象分割のみ・他保持 | `tests/test_test_pre_group.py::test_group_prepare_isolated` | はい | 固定画像と段階公開 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-002 | REQ-003 | REQ-003-S02 | integration | 位置合わせ失敗 | 未判定と再撮影要否 | `tests/test_test_pre_group.py::test_group_alignment_failure` | はい | 失敗ダブル | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-003 | REQ-003 | REQ-003-S03 | integration | 範囲外の単独準備 | グループID・画像名・分割IDの表示と旧成果物保持 | `tests/test_test_pre_group.py::test_group_crop_failure` | はい | 固定画像とCLI記録 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-004 | REQ-003 | REQ-003-S04 | integration | 読込み不能画像 | グループID・画像名の表示と旧成果物保持 | `tests/test_test_pre_group.py::test_group_read_failure` | はい | 不正画像とCLI記録 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-005 | REQ-003 | REQ-003-S05 | integration | 残存stageで再実行 | stage整理 | `tests/test_test_pre_group.py::test_group_stale_stage` | はい | ファイル操作 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-006 | REQ-003 | REQ-003-S06 | integration | 全件準備 | ID順・全領域 | `tests/test_test_pre_group.py::test_all_groups_prepare` | はい | 固定画像 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-007 | REQ-003 | REQ-003-S07 | integration | 未知ID | 旧成果物保持・2 | `tests/test_test_pre_group.py::test_unknown_group` | はい | CLI入力 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-008 | REQ-025 | REQ-025-S01 | integration | 学習準備 | IDと指紋 | `tests/test_test_pre_group.py::test_training_manifest_unchanged` | はい | manifest | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-009 | REQ-025 | REQ-025-S02 | integration | 単独試験準備と設定変更 | 指紋・ID・除外項目 | `tests/test_test_pre_group.py::test_testing_group_fingerprint` | はい | manifest | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-010 | REQ-025 | REQ-025-S03 | unit | 輝度条件変更 | 指紋変更 | `tests/test_test_pre_group.py::test_brightness_fingerprint` | はい | 設定指紋 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-011 | REQ-025 | REQ-025-S04 | unit | 検査値変更 | 指紋不変 | `tests/test_test_pre_group.py::test_inspection_value_fingerprint` | はい | 設定指紋 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-012 | REQ-041 | REQ-041-S01 | integration | 単独検査 | 指定準備だけを使用 | `tests/test_test_pre_group.py::test_single_evaluation_uses_group` | はい | 検査ダブル | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-013 | REQ-041 | REQ-041-S02 | integration | 全件検査 | 全準備を照合 | `tests/test_test_pre_group.py::test_all_evaluation_uses_groups` | はい | 検査ダブル | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| TC-014 | REQ-041 | REQ-041-S03 | integration | 準備manifest欠落・指紋不一致 | 対象IDと再準備案内を表示し、両グループの旧結果保持 | `tests/test_test_pre_group.py::test_evaluation_rejects_bad_group` | はい | manifest削除・改変と検査前照合 | 実画像 (3.2) | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-003 | 7 | 7 | なし | 網羅 |
| REQ-025 | 4 | 4 | なし | 網羅 |
| REQ-041 | 3 | 3 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 2グループの単独準備・検査と他成果物保持 | pytestと成果物読戻し | 対象OS実画像 (3.2) | 未検証 | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| AC-002 | 全件準備・全件検査 | pytestと成果物読戻し | 対象OS実画像 (3.2) | 未検証 | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| AC-003 | 未知ID、失敗、欠落・不整合 | pytestと旧成果物比較 | 対象OS実画像 (3.2) | 未検証 | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
| AC-004 | Ubuntu 24.04 LTSとApple silicon macOSの実画像 | 全工程実行と画像・JSON読戻し | 対象環境で未実施 (3.2) | 未検証 | openspec/changes/archive/2026-10-27-add-test-pre-group/evidence/implementation.md |
