## 1. 入力・パス・接続の契約

- [x] 1.1 `src/app/common/config.py` の `inspection_threshold` 検証で巨大整数の `OverflowError` を有限数値違反として扱い、項目を示す入力不備へ渡す。対応: `REQ-021`、設計「データ契約と状態」「技術判断: 巨大整数の数値検証」、`TC-001`〜`TC-006`。完了条件: 既存の有効値・不正値の扱いを保ち、巨大整数で5 CLIが終了コード2を返す。
- [x] 1.2 `src/app/common/paths.py` の共通リンク拒否エラーを、用途名ではなく検出したリンク自体のパスを主語とする文言にする。対応: `REQ-039`、設計「インターフェースと失敗時の結果」「技術判断: シンボリックリンクのエラー」、`TC-007`。完了条件: 設定・準備・成果物のリンク拒否で対象パスを判別でき、リンク先が不変である。
- [x] 1.3 `src/app/model_training/search.py` の `create_study` でストレージハンドルを必須にし、内部で新規接続を作る分岐を削除して既存呼び出し元を更新する。対応: `REQ-040`、設計「データ契約と状態」「技術判断: 探索接続の所有と終了順序」、`TC-008`、`TC-009`。完了条件: 学習CLIから渡した接続だけを使用し、呼び出し元が閉鎖できる。
- [x] 1.4 `src/app/model_training/cli.py` で探索中・公開前の失敗時を含め、ストレージ接続の終了後に失敗グループの一時領域を削除する。成功時の公開前閉鎖と旧成果物の保全を維持する。対応: `REQ-040`、設計「処理フロー」「技術判断: 探索接続の所有と終了順序」、`TC-008`、`TC-009`。完了条件: 失敗理由を保持し、接続終了が一時領域削除より先になる。

## 2. シナリオの自動試験

- [x] 2.1 `tests/test_config.py` の pytest `TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005` に対応する既存試験を実行・必要に応じて更新し、`TC-006` の `test_inspection_threshold_huge_integer_is_input_error` を追加する。対応: `REQ-021` / `REQ-021-S01`〜`REQ-021-S06` / `TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`、`TC-006`、設計「試験設計」。完了条件: 巨大整数で全5 CLIの終了コード2、ID・項目・理由、成果物不変と既存境界条件を pytest で確認する。
- [x] 2.2 `tests/test_config.py::test_symlink_error_identifies_rejected_path` の pytest 試験を追加し、設定・準備・成果物の親と末端のリンク拒否を検証する。対応: `REQ-039` / `REQ-039-S01` / `TC-007`、設計「試験設計」。完了条件: エラーに拒否したリンク自体のパスが含まれ、終了コード2でリンク先と既存成果物が不変である。
- [x] 2.3 `tests/test_training.py` に pytest `test_storage_closes_before_failed_stage_cleanup` と `test_storage_closes_before_publication_failure_cleanup` を追加し、失敗注入と再実行を検証する。対応: `REQ-040` / `REQ-040-S01`・`REQ-040-S02` / `TC-008`、`TC-009`、設計「試験設計」。完了条件: 実ストレージ接続の終了が一時領域削除より先で、旧成果物保全と新規探索の再実行を確認する。

## 3. 品質・対象環境の受け入れ

- [x] 3.1 `npx --no-install openspec validate polish-review-leftobers --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change polish-review-leftobers --phase implementation`、`npm run check` を実行し、全 `TC-001`〜`TC-009` の収集・成功と品質ゲートを記録する。対応: `REQ-021`、`REQ-039`、`REQ-040`、設計「試験設計」「網羅性確認」。完了条件: 全コマンドが成功し、失敗を残さない。
- [ ] 3.2 Ubuntu 24.04 LTS (ネイティブまたは WSL2) と Apple silicon macOS の対象環境で、AC-001の巨大整数入力、AC-002のリンク拒否、AC-003の学習失敗と再実行、AC-004の `check` → `train-pre` → `train` → `test-pre` → `test` の全再実行と成果物読戻しを確認する。対応: `AC-001`〜`AC-004`、設計「受け入れ検証」。完了条件: `evidence/acceptance.md` に実行日、OS・Python・依存版、実行コマンド、対象データ、結果、制約を記録し、全ACの状態と残る検証を更新する。対象環境を利用できない場合は未検証のまま残す。
- [x] 3.3 verify / archive 前に厳密検証とトレーサビリティ検査を実行する。通常は `--phase complete`、対象環境の確認だけを延期する制限付きアーカイブでは `--phase limited-archive` を使用し、延期対象の change 名・AC-ID・未完了タスク番号・確認内容を README の「延期中の受け入れ確認」へ引き継ぐ。対応: `AC-001`〜`AC-004`、設計「受け入れ検証」「移行とロールバック」。完了条件: 選択した工程の検査に成功し、延期する場合は利用者に残るリスクを示して明示的な了承を得る。
