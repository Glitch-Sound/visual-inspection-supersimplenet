## 背景・前提

`test` は現在、グループごとに全元画像を処理し、各グループの処理開始時に進捗を作り直す。<br />
結果世代は全対象グループの処理後に一度だけ公開する。<br />
既存の試験にはScenario IDを名前に含みながら別の結果を検証するものがある。

## 要件トレーサビリティ

| 要件ID | 責務・境界 | 設計節 | 実装タスク | TC-ID | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| NREQ-003 | 検査CLIの進捗 | 処理フロー、インターフェースと失敗時の結果 | 1.1、1.2 | TC-001、TC-002、TC-003、TC-004 | 全・単独グループで一進捗の出力と失敗時件数をpytestで確認 |
| REQ-020 | グループの明示的再学習 | データ契約と状態、移行とロールバック | 3.1 | TC-005、TC-006 | 指定グループの重み・保存結果・他グループ保持をpytestで確認 |
| REQ-003 | 試験準備の結果保存 | データ契約と状態 | 3.5 | TC-007〜TC-010 | 正常・失敗・保全と再撮影要否をpytestで確認 |

## 業務フローと責務

`src/app/model_evaluation/cli.py` は一回の検査に一つの進捗を持つ。<br />
`src/app/model_evaluation/evaluation.py` はグループ・元画像の結果確定を通知する。<br />
`src/app/model_training/` は指定グループだけの再学習を継続する。<br />
学習・画像準備・評価の試験では、Scenario名と実際の期待値を一致させる。

## 処理フロー

1. 検査開始時に試験manifestから元画像総数を得て、単一進捗を`0/総数`で開始する。
2. 既存のグループ別結果生成順序を維持する。各元画像の結果JSONをステージへ保存した直後に通知し、最後の対象グループで確定した元画像だけ進める。先行グループの途中では進めない。
3. 最後の一件の表示は、全結果JSONに最終実行記録を書き、現行結果参照の公開に成功するまで保留する。後続グループ、結果画像・JSON、最終書込み、公開で失敗した場合は未完了件数を表示せず、結果参照を切り替えない。
4. 単独グループでも同じ進捗を使う。未判定・個別推論エラーは元画像結果が確定した場合に一件進める。

## データ契約と状態

進捗は標準エラーの表示だけを変更する。<br />
試験準備の位置合わせ失敗では、準備manifestの位置合わせ結果に`recapture_required=true`を保存し、従来どおりCLIで再撮影の警告を出す。<br />
共通の位置合わせ契約を使用するため、学習・試験準備manifestと検査結果JSONの`alignment`にも`recapture_required`を出力する。位置合わせ成功時は`false`とする。<br />
標準出力の実行記録JSON、終了コード、結果画像、`current.json` は現行契約を維持する。<br />
REQ-020は既存の`--group`と`--restart`を用いる。旧形式の学習成果物を読み込む契約は追加しない。

## インターフェースと失敗時の結果

| 操作 | 入力 | 結果 | 失敗時 |
| --- | --- | --- | --- |
| 全グループ`test` | 型番、試験準備、全グループの学習成果物 | 元画像総数に対して一つの進捗とグループ別結果 | 失敗グループを示し、未完了元画像を数えず現行結果を保持 |
| 単独グループ`test` | 型番とグループID | 同じ形式の一つの進捗 | 現行結果を保持 |
| グループの`train --restart` | 型番とグループID | 指定グループの新しいcheckpoint・暫定閾値 | 失敗理由を示し、他グループの成果物を保持 |

## 技術判断

### 判断: グループ処理順序と進捗

- **状態**: 確定。
- **採用内容**: 現行のグループ別の結果生成順序を維持し、最後の対象グループの元画像結果確定をコマンド進捗へ反映する。
- **根拠**: 現行結果の原子公開と失敗時保全を変更せず、全対象グループを終えた元画像だけ数えられる。
- **代替案**: 元画像ごとに全グループを処理する方式は結果生成順序とモデル読込み範囲を大きく変更するため採用しない。
- **不変条件**: 開始表示は一回、件数は元画像総数以下、標準出力JSONは一件、公開前失敗で旧結果保持。

## 境界条件と失敗モード

| 事象 | 状態変更 | 表示と復旧 |
| --- | --- | --- |
| 先行グループで失敗 | 現行結果を変更しない | 進捗は0または既に全グループで確定した件数のみ。理由を示して再実行する |
| 最後のグループで個別推論エラー | 元画像結果を未判定として確定 | 当該元画像を一件進め、エラーを結果へ残す |
| 結果画像または結果JSONの書込み失敗 | 現行結果を変更しない | 保存が済んでいない元画像を進めず、失敗グループを表示する |
| 最終結果JSONの書込みまたは現行参照の公開失敗 | 現行結果を変更しない | 最後の一件を進めず、失敗理由を表示する |

## セキュリティ・性能・運用

進捗のための結果再読込みや追加のモデル構築は行わない。<br />
対象OS・GPUの確認は既存の延期記録の範囲であり、この変更によって検証済み扱いにしない。

## 移行とロールバック

旧形式成果物の移行は不要である。<br />
進捗表示だけの変更はコードの差戻しで復元でき、保存済み結果の変換は不要である。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | NREQ-003 | NREQ-003-S01 | integration | 端末・複数グループで検査 | 一進捗で元画像総数まで到達しJSON一件 | `tests/test_evaluation.py::test_command_progress_tty_once_per_source` | はい | 端末表示の契約 | 対象OSの端末表示 | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-002 | NREQ-003 | NREQ-003-S02 | integration | 非端末・複数グループで検査 | 0から総数まで一度ずつ表示しJSON一件 | `tests/test_evaluation.py::test_command_progress_non_tty_once_per_source` | はい | 非端末表示の契約 | 対象OSの非端末表示 | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-003 | NREQ-003 | NREQ-003-S03 | integration | 未判定・個別推論エラーを含む検査 | 確定した元画像だけ進め、警告・エラー・終了コードを維持 | `tests/test_evaluation.py::test_command_progress_counts_undetermined` | はい | 元画像結果と進捗。CLIの終了状態は別試験で確認 | 対象OSの表示 | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-004 | NREQ-003 | NREQ-003-S04 | integration | 後続グループまたは結果JSONの保存で処理全体失敗 | 未完了件数を進めず旧参照保持し、CLIで失敗理由・終了コードを示す | `tests/test_evaluation.py::test_command_progress_stops_on_failure` | はい | 進捗と保全。CLIの失敗表示・終了コードは別試験で確認 | 対象OSの表示 | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-005 | REQ-020 | REQ-020-S01 | integration | 指定グループを再学習 | 指定重みのcheckpointと閾値を保存しcheckpointから推論する | `tests/test_training.py::test_group_restart_uses_tv_backbone` | はい | モデル構築と成果物・推論の契約。実学習・実重みは対象外 | 実重み・対象OS | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-006 | REQ-020 | REQ-020-S02 | integration | 既存履歴と検査結果を持つ指定グループを再学習 | その履歴とモデルだけを置換し、新閾値・表示範囲を確認して検査結果を再生成。他グループ保持 | `tests/test_training.py::test_group_restart_replaces_only_selected_history` | はい | グループ単位の置換と再検査契約。実重みは対象外 | 実モデル・対象OS | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-007 | REQ-003 | REQ-003-S01 | integration | 有効な試験元画像を準備 | 分割画像と元画像の対応を保存 | `tests/test_preparation.py::test_req_003_s01` | はい | 保存済み分割画像 | 実画像・対象OS | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-008 | REQ-003 | REQ-003-S02 | integration | 位置合わせ失敗をCLIで準備 | 未判定・失敗理由・再撮影要否を保存して警告 | `tests/test_preparation.py::test_req_003_s02` | はい | manifestとCLI表示 | 実画像・対象OS | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-009 | REQ-003 | REQ-003-S03 | integration | 分割範囲外の元画像を準備 | 元画像名と分割IDで失敗 | `tests/test_preparation.py::test_req_003_s03` | はい | 範囲外の拒否 | 実画像・対象OS | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| TC-010 | REQ-003 | REQ-003-S04 | integration | 読込み不能画像で再準備 | 途中成果物破棄と旧結果保持 | `tests/test_preparation.py::test_req_003_s04` | はい | 保存済み結果の保全 | 実画像・対象OS | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |

TC-003のCLI終了記録と検査結果JSONの再撮影要否は`tests/test_evaluation.py::test_command_progress_cli_undetermined_exit_record`で補足する。<br />
TC-004のCLI失敗表示・終了コード・旧参照保持は`tests/test_evaluation.py::test_command_progress_cli_failure_exit_record`で補足する。

既存仕様の試験補修では、`REQ-003-S01`〜`S04`、`REQ-017-S01`〜`S02`、`REQ-005-S02`、`REQ-007-S02`〜`S05`、`REQ-010-S01`〜`S04`、`REQ-018-S04`、`REQ-019-S01`、`NREQ-002-S01`〜`S02`、`NREQ-004-S01`〜`S03`、`REQ-009-S01`〜`S02`を対象とする。<br />
既存のScenario IDを持つ試験は、期待値を直接確認するよう改修する。別名の試験が同じ期待値を確認する場合は対応関係を明示し、重複だけの試験を増やさない。

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| NREQ-003 | 4 | 4 | なし | 設計済み |
| REQ-020 | 2 | 2 | なし | 設計済み |
| REQ-003 | 4 | 4 | なし | 設計済み |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | macOSの全・単独グループと失敗時の進捗 | TC-001〜TC-004、CLI出力の照合 | 実端末・対象OSはREADMEで追跡 | 未検証 | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| AC-002 | macOSのScenario期待値と試験の対応 | 補修試験と品質ゲート | 実画像・対象OS・実GPUはREADMEで追跡 | 未検証 | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
| AC-003 | グループの再学習と他グループ保持 | TC-005、TC-006と仕様の照合 | 実重み・対象OSはREADMEで追跡 | 未検証 | openspec/changes/align-inspection-progress-and-scenario-tests/evidence/acceptance.md |
