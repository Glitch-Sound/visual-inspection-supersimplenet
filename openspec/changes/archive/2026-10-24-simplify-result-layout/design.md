## 背景・前提

現行の `src/app/model_evaluation/cli.py` は `result_index.py` で一時領域・世代・`current.json` を管理し、グループごとに評価直後に公開する。<br />
`src/app/common/cli.py` は全CLIで世代整理を行い、`ProjectPaths` は世代・現行参照のパスを持つ。<br />
`src/app/image_preparation/preparation.py` には、一時ディレクトリを作成して旧ディレクトリを置換する処理がある。<br />
ユーザー指定により旧成果物との互換性と移行は不要である。結果領域のシンボリックリンク拒否は維持し、公開途中の中断は旧結果の退避と復旧で扱う。

## 目標・対象外

### 目標

- 全対象グループを完成させてから、固定したグループ別ディレクトリへ公開する。
- 公開前失敗で旧結果を保持し、公開中断後にグループ単位の完全な結果へ復旧する。
- 結果領域の管理対象だけを置換・整理し、準備処理と検査処理の共通ディレクトリ操作を一か所に置く。

### 対象外

- 旧 `current.json`、`generations/` と旧準備・学習成果物の移行・削除。
- 推論、判定、JSON本文、可視化画像の内容変更。
- 同時検査中に外部プロセスが直接結果ディレクトリを読み続ける場合の無停止参照。型番ロックでCLI同士は直列化し、読み手は検査停止・復旧後に参照する。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-013 | 処理フロー、技術判断、境界条件と失敗モード | 一時結果・退避・復旧・整理 | 1.1、2.1、2.2、3.2、3.3 | TC-001～TC-011 | 故障点注入と保存状態をpytestで確認 |
| NREQ-003 | 処理フロー、インターフェースと失敗時の結果 | 検査進捗と完了表示 | 2.2、3.4 | TC-012～TC-015 | 端末・非端末と失敗時の進捗をpytestで確認 |
| REQ-023 | 処理フロー、インターフェースと失敗時の結果 | 対象選択・学習成果物照合・公開前失敗 | 2.2、3.2 | TC-016～TC-020 | 全件・単独・不足モデルをpytestで確認 |
| REQ-028 | データ契約と状態、移行とロールバック | 固定結果パスとファイル構成 | 1.2、2.2、3.1 | TC-021～TC-022 | 境界IDと旧ファイル除去をpytestで確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 結果パスの生成・安全確認 | 変更 | 型番、グループID | 固定したグループ別パスまたは拒否 | `ProjectPaths` | `src/app/common/paths.py` に確定。既存の全成果物パス境界のため |
| ディレクトリの段階作成・置換 | 共通化 | 対象パス、作成処理 | 完全な新ディレクトリ | 準備・検査 | `src/app/common/atomic.py` に確定。既存準備処理の責務を抽出するため |
| 検査結果の一時管理・復旧 | 変更 | 型番結果ルート、対象グループ | ステージ、退避、復旧済み結果 | 共通置換、パス検証 | `src/app/common/result_index.py` に確定。世代・参照管理を除き結果専用管理を残すため |
| 検査と公開の順序 | 変更 | 型番、対象グループ、準備・学習成果物 | グループ結果、CLI表示 | 評価処理、結果専用管理 | `src/app/model_evaluation/cli.py` に確定。既存の `test` 入口のため |
| 全CLIの旧整理呼出し | 削除 | 型番 | 結果への副作用なし | 共通CLI | `src/app/common/cli.py` に確定。旧世代整理だけを外す |
| 成果物の利用案内・実機読戻し | 変更 | 新保存契約 | READMEの新パス・再実行手順とスモーク試験の読戻し | 運用者 | `README.md` と `scripts/run_visual_inspection_smoke.py` に確定 |

### 処理フロー

1. `test` は型番設定、対象グループ、試験manifestを照合し、型番ロック内で結果ルートと各グループのパスをシンボリックリンク検査する。<br />
   既存の退避があれば復旧し、管理対象の残留ステージを整理する。復旧できなければ理由を示して停止する。
2. 結果ルート直下に一時ディレクトリを一つ作り、全対象グループについて既存の評価処理で結果画像と元画像別JSONを生成する。<br />
   一つでも失敗すればステージを削除し、旧結果には触れない。
3. 全対象が完成したらグループID順に公開する。既存のグループディレクトリを同じ結果ルート内の退避名へ移し、完成した新グループを固定パスへ移す。<br />
   旧結果の退避と新結果の移動の間で通常の例外が出た場合は、その場で旧結果を復元する。強制終了後は次回開始時に退避と固定パスを照合し、固定パスがなければ旧結果を復元する。固定パスに新結果があれば新結果を維持して退避を整理する。
4. 全件検査だけは、設定にない正規のグループディレクトリを結果ルートから整理する。`--group` 時は他グループを調べて置換・削除しない。<br />
   `current.json`、`generations/`、その他の管理外エントリには触れない。
5. 全公開後に進捗を総件数へ進め、結果ルートを表示する。評価者は検査停止・復旧後に固定パスから結果を読む。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| グループ結果 | 変更 | `group_<2桁以上のID>/` にJSON・PNG | 直下は `<元画像名>.json` と `<分割画像名>_result.png` のみ。結果JSON本文は既存契約 | 評価CLI | 旧世代から移行しない |
| 結果ステージ | 変更 | `data/06_result/<model>/.stage-<UUID>/` | 一回の検査の全対象グループを格納。公開前に外部へ示さない | 結果専用管理 | 中断後に管理対象だけ整理 |
| グループ退避 | 追加 | `data/06_result/<model>/.backup-<正規グループ名>-<UUID>/` | 完全な旧結果を一時保持。固定パスがなければ復元し、新結果があれば整理 | 結果専用管理 | 旧 `generations/` とは別 |
| 現行参照・結果世代 | 削除 | 新結果に `current.json` と `generations/` を作らない | 既存ファイルを移行・自動削除しない | 旧専用管理を削除 | 新旧の混在利用はしない |
| 完了表示 | 変更 | 型番結果ルートのパス | `current.json` のパスを表示しない | 評価CLI | 表示契約が変わる |

ステージと退避は結果ルート内でのみ作り、正規の命名規則に一致する自らの管理対象だけを整理する。<br />
結果グループ内にシンボリックリンクまたは期待外のエントリがあれば、退避・削除せず入力不備として停止する。グループIDは従来どおり整数であり、名称だけ最低2桁の0埋めとする。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `test` | 運用者 → 評価CLI | 有効な型番、任意のグループID | 固定パスの結果と結果ルート表示 | 不正入力・欠落モデル → グループと理由、旧結果保持 | 原因を直して再実行。型番ロックで競合拒否 |
| 結果パス取得 | 評価CLI → `ProjectPaths` | 型番、非負のグループID | 管理領域内のパス | 親または対象がリンク → 拒否、外部不変 | 再取得可 |
| ステージ・公開・復旧 | 評価CLI → 結果専用管理・共通置換 | 全対象の完成済み結果 | グループ単位の新結果 | 中断・移動失敗 → 旧結果復元または次回復旧。復旧不能なら停止 | 再実行時に管理対象だけ整理 |
| 進捗・終了表示 | 評価CLI → 運用者 | 元画像総数、公開結果 | 最終公開後に総件数と結果ルート | 公開失敗 → 総件数へ進めず失敗を表示 | 再実行可 |

## 技術判断

### 判断・候補: 退避付きのグループ置換

- **状態**: 確定。ユーザーは退避と復旧を認め、グループの完全性を優先した。
- **採用内容 / 候補**: ステージへ全件を作成後、旧ディレクトリを同じ結果ルート内へ退避し、新ディレクトリを固定名へ移す。次回開始時に退避を検出して復旧する。
- **根拠**: 旧ディレクトリを削除してから新ディレクトリを移すだけでは、その間の強制終了で完全な結果を保証できない。退避があれば旧結果を戻せる。
- **代替案**: 削除後の移動は欠落を許容するため不採用。OS固有のディレクトリ交換は対象OS間で同じ契約にしにくいため採らない。
- **実装規則 / 不変条件**: 公開前に全対象グループを完成させる。退避は新結果の公開確認または旧結果の復元まで削除しない。強制終了直後は固定パスが一時的に欠け得るため、次の検査開始時に復旧を完了させる。CLI外の直接読取りは検査停止・復旧後に行う。
- **影響**: WindowsとUbuntuで同一結果ルート内の移動を使う。中断時は次回起動時に復旧処理が必要になる。

### 判断・候補: 共通のディレクトリ操作

- **状態**: 確定。
- **採用内容 / 候補**: `preparation.py` の段階作成・置換の基礎処理を `common/atomic.py` に移し、準備と検査から利用する。結果専用のグループ列挙・退避復旧は `result_index.py` に残す。
- **根拠**: 両処理は同じファイルシステム上の段階作成と移動を共有するが、結果の対象選択と復旧は検査固有である。
- **代替案**: 結果専用処理へ全部複製すると安全確認が二重化するため採らない。
- **実装規則 / 不変条件**: `common/` は個別能力をimportしない。準備の既存の正常系・失敗系を保つ。結果領域で管理外エントリを削除しない。
- **影響**: 準備、共通、評価の各パッケージと既存準備テスト。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 作成中の後続グループ失敗 | 評価CLI | ステージ削除、全旧結果保持 | 失敗グループIDと理由 | CLI実行記録 | 入力を直して全件再実行 |
| 退避後・移動前の例外 | 結果専用管理 | 旧結果を固定パスへ戻す | 公開失敗を表示 | CLI実行記録 | 戻せなければ退避を残し次回復旧 |
| 公開途中の強制終了 | 次回の結果専用管理 | 固定パスがなければ旧を戻し、固定パスに新があれば維持 | 復旧後に利用可。不能なら理由付きで拒否 | CLI警告・エラー | 全グループ再検査で新旧混在解消 |
| 対象・親のシンボリックリンク | パス・結果専用管理 | 読書き削除しない | 不正パスを示して拒否 | CLIエラー | リンクを安全な実ディレクトリに直す |
| 管理外エントリ | 結果専用管理 | 当該エントリに触れない。対象グループ内なら置換拒否 | 不正な対象を示す | CLIエラー | 運用者が内容を確認する |
| 旧形式の残存 | 結果専用管理 | 読まず、削除しない | 新結果のみを表示 | 追加記録なし | 必要なら運用者が別途整理 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| パス安全性 | 型番・グループ名を検証し、結果ルートまでの全要素と置換対象のリンクを拒否する。削除対象は正規のグループ名と管理対象一時名に限定する | リンク先と管理外ファイルの不変をTC-005、TC-009、TC-010で確認 |
| 性能 | 新結果全件を一時保存してから公開する。新たな所要時間上限は設定しない | CLIの処理時間と対象OS実行結果を記録 |
| 運用 | 結果の外部読取りは同型番の検査停止・復旧後に行う。公開途中で停止した場合は再起動時の復旧を確認し、必要なら全件検査する | TC-004と対象OSのAC-003、AC-005で確認 |

認証・認可と外部通知は追加しないため、既存ローカルCLIの範囲を維持する。

## 移行とロールバック

1. 新版では旧成果物を利用せず、`train-pre`、`train`、`test-pre`、`test` の順に再実行する。分割位置の確認が必要なら先に `check` を実行する。
2. 新結果がグループ別固定パスで読めることを確認する。旧 `current.json` と `generations/` は自動移行・自動削除しない。
3. ロールバックする場合は旧コードと対応する旧成果物一式に戻す。新旧成果物を混在利用しない。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-013 | REQ-013-S01 | integration | 旧結果から全件再検査 | 全件完成後に新結果だけ公開 | `tests/test_evaluation.py::test_result_replace_after_all_groups_complete` | はい | CLIと保存状態、予測ダブル | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-002 | REQ-013 | REQ-013-S02 | integration | 2グループから単独再検査 | 他グループの内容・時刻は不変 | `tests/test_evaluation.py::test_result_single_group_preserves_others` | はい | CLIと保存状態、予測ダブル | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-003 | REQ-013 | REQ-013-S03 | integration | 後続グループの作成に失敗 | 全旧結果保持、一時領域削除 | `tests/test_evaluation.py::test_result_stage_failure_preserves_all_groups` | はい | 故障注入と保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-004 | REQ-013 | REQ-013-S04 | integration | 退避直後・公開直後に中断を模擬し再開 | 旧または新を完全に復旧、不能時拒否 | `tests/test_evaluation.py::test_result_recovery_after_publish_interrupt` | はい | 故障注入と復旧。実強制終了は別 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-005 | REQ-013 | REQ-013-S05 | integration | 親・対象をリンクにして検査 | 拒否しリンク先不変 | `tests/test_evaluation.py::test_result_rejects_symlink_paths` | はい | パス検証と領域外不変 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-006 | REQ-013 | REQ-013-S07 | integration | 新旧混在から全件再検査 | 全設定グループが新結果 | `tests/test_evaluation.py::test_result_full_rerun_replaces_mixed_groups` | はい | CLIと保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-007 | REQ-013 | REQ-013-S08 | integration | 残存ステージ下で準備CLIを実行 | 検査結果を理由に拒否しない | `tests/test_evaluation.py::test_result_residue_does_not_block_preparation` | はい | 共通CLIの非干渉 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-008 | REQ-013 | REQ-013-S09 | integration | 設定外の正規グループと旧形式を置く | 全件後に設定外グループだけ削除 | `tests/test_evaluation.py::test_result_full_run_removes_unconfigured_groups` | はい | 整理対象、旧形式不変 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-009 | REQ-013 | REQ-013-S10 | integration | 残存ステージ・退避と管理外ファイル | 管理対象だけ復旧・整理 | `tests/test_evaluation.py::test_result_cleanup_managed_entries_only` | はい | 復旧と管理外不変 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-010 | REQ-013 | REQ-013-S11 | integration | 後続グループ評価に故障注入 | 全旧結果、失敗IDと理由 | `tests/test_evaluation.py::test_result_later_group_failure_keeps_all_old` | はい | CLI失敗記録と保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-011 | REQ-013 | REQ-013-S12 | integration | 旧一時領域を残して検査 | 残留領域整理後に公開 | `tests/test_evaluation.py::test_result_stale_stage_removed` | はい | 残留領域と保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-012 | NREQ-003 | NREQ-003-S01 | integration | 端末扱いで複数元画像検査 | 単一バー、最後に総件数 | `tests/test_evaluation.py::test_result_tty_progress` | はい | stderr進捗とstdout JSON | 対象OS端末 (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-013 | NREQ-003 | NREQ-003-S02 | integration | 非端末で複数元画像検査 | 0から総件数、stdout JSON一件 | `tests/test_evaluation.py::test_result_non_tty_progress` | はい | stderr進捗とstdout JSON | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-014 | NREQ-003 | NREQ-003-S03 | integration | 未判定・分割エラーの元画像 | 確定した元画像だけ加算 | `tests/test_evaluation.py::test_result_progress_counts_undetermined` | はい | 進捗とJSON判定 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-015 | NREQ-003 | NREQ-003-S04 | integration | 最終公開に故障注入 | 総件数を表示せず失敗 | `tests/test_evaluation.py::test_result_publish_failure_does_not_finish_progress` | はい | 故障注入とstderr | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-016 | REQ-023 | REQ-023-S01 | integration | 全件検査 | 全グループの元画像別結果 | `tests/test_evaluation.py::test_result_all_groups` | はい | CLIと保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-017 | REQ-023 | REQ-023-S02 | integration | 単独検査 | 指定グループだけ更新 | `tests/test_evaluation.py::test_result_selected_group` | はい | CLIと保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-018 | REQ-023 | REQ-023-S03 | integration | 後続グループのモデルを欠損 | IDと欠損名、全旧結果保持 | `tests/test_evaluation.py::test_result_missing_model_preserves_all` | はい | 照合と失敗記録 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-019 | REQ-023 | REQ-023-S04 | integration | 未定義グループを指定 | 利用可能IDと旧結果保持 | `tests/test_evaluation.py::test_result_unknown_group` | はい | 設定検証と保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-020 | REQ-023 | REQ-023-S05 | integration | 後続グループの評価失敗 | 全旧結果保持 | `tests/test_evaluation.py::test_result_full_run_failure_preserves_all` | はい | 故障注入と保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-021 | REQ-028 | REQ-028-S01 | integration | ID 0、9、10、100で検査 | 固定名、JSON・PNGだけ、整数ID、結果ルート表示 | `tests/test_group_artifact_names.py::test_result_group_names` | はい | パスとCLI、予測ダブル | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| TC-022 | REQ-028 | REQ-028-S02 | integration | 旧結果に余分な元画像結果を置く | 今回の結果だけ残る | `tests/test_evaluation.py::test_result_rerun_drops_old_source_files` | はい | 保存状態 | 対象OS (3.6) | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-013 | 11 | 11 | なし | 網羅 |
| NREQ-003 | 4 | 4 | なし | 網羅 |
| REQ-023 | 5 | 5 | なし | 網羅 |
| REQ-028 | 2 | 2 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | Ubuntu 24.04 LTSとWindows 11で保存名・直下構成・読戻し・完了表示 | TC-001、TC-021、TC-022と対象OSの `test` 結果確認 | 対象OS確認 (3.6) | 未検証 | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| AC-002 | 両OSで全件・単独、設定外グループ、他グループ保全 | TC-002、TC-006、TC-008、TC-016、TC-017と対象OSの再検査 | 対象OS確認 (3.6) | 未検証 | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| AC-003 | 両OSで公開前失敗、公開途中の強制終了・復旧 | TC-003、TC-004、TC-009、TC-010、TC-011と対象OSの中断試験 | 対象OS確認 (3.6) | 未検証 | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| AC-004 | 両OSで親・対象のリンク拒否と管理外ファイル不変 | TC-005、TC-008、TC-009と対象OSのパス試験 | 対象OS確認 (3.6) | 未検証 | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
| AC-005 | 両OSで準備・学習・検査の全再実行と新結果読戻し、旧形式不変 | 全TCと対象OSの全CLIスモーク、旧形式の事前・事後比較 | 対象OS確認 (3.6) | 未検証 | `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/implementation.md` |
