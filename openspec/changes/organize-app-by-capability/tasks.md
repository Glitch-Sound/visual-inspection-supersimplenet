## 1. 検査基盤と共通契約

- [x] 1.1 `scripts/check_openspec_traceability.py` と `tests/test_check_openspec_traceability.py` に、`.openspec.yaml` の `skip_specs: true` を明示した change 専用の検査経路を追加する。proposal の AC-ID と design のトレーサビリティ行・単一 pytest 参照の TC 行・tasks の参照番号を照合し、design 段階は形式と対応、implementation 段階はテスト収集、complete 段階は全タスク完了と既存の受け入れ証跡検査を実行する。通常の spec 付き change の REQ/Scenario 検査は維持する。対応: `AC-004`、設計「判断4」「試験設計」、`TC-004`。完了条件: `tests/test_check_openspec_traceability.py::test_skip_specs_change_checks_design_tasks_and_acceptance` と、この change の設計段階検査が成功する。実行時コードの移動に先行する。

- [x] 1.2 `src/app/common/` を作り、既存の `atomic.py`、`config.py`、`contracts.py`、`paths.py`、`runtime.py` と、`imaging.py` の `ImageArray`・`ImageReadError`・画像入出力、`modeling.py` の共通モデル生成を設計の配置表どおりに移す。`training.py` の journal 名・stage/backup パス・一時ファイル除去と `recover_artifact_transaction` を `common/artifact_transaction.py` に置き、既存のファイル名・内容・復旧順序を維持する。journal 書込みと stage 置換は移さない。型・検証規則・シリアライズを変更しない。対応: `AC-001`、`AC-003`、既存 `REQ-001`〜`REQ-013`、設計「確定した配置」「データ契約と状態」「判断1・2」、`TC-001`、`TC-003`、`TC-007`。完了条件: 共通モジュールに能力専用の import がなく、既存設定と成果物の読戻し・学習成果物一式の復旧が同じ結果になる。

- [x] 1.3 `src/app/common/cli.py` に現行 `_run` と `ExitCode` を移し、例外分類、実行記録、標準出力を維持する。対応: `AC-002`、既存 `NREQ-001`、設計「インターフェースと失敗時の結果」「判断3」、`TC-006`。完了条件: 成功 exit 0、入力・契約不備 exit 2、処理失敗 exit 3 と出力 JSON の項目が従来どおりである。

## 2. 能力別の実装配置

- [x] 2.1 `src/app/image_preparation/` に画像準備 CLI、ORB・crop・描画、確認画像と学習・試験準備を移す。`check`、`train-pre`、`test-pre` の処理と警告、原子的置換を維持し、参照先を `common/` に更新する。対応: `AC-001`、`AC-002`、`AC-003`、既存 `REQ-001`〜`REQ-003`、設計「確定した配置」「処理フロー」「判断1」、`TC-001`〜`TC-003`。完了条件: 画像準備の既存正常・失敗・未判定テストが成功し、他能力を import しない。

- [x] 2.2 `src/app/model_training/` に学習 CLI・結果表示文、学習時拡張、データ分離・探索と `TrialRunner`、Anomalib 試行、予測スコア抽出、事前学習重みの `ensure_cached`、journal 書込み・stage 置換・checkpoint メタデータ付与・成果物一式更新の組立てを設計の配置表どおりに移す。学習 CLI と保存処理は `common/artifact_transaction.py` の復旧・journal 名・stage/backup パス・後片付けを使用し、閾値算出と通常再開・`--restart` の処理を維持する。対応: `AC-001`、`AC-002`、`AC-003`、既存 `REQ-004`〜`REQ-008`、設計「確定した配置」「処理フロー」「判断1・2」、`TC-001`〜`TC-003`、`TC-007`。完了条件: 学習の既存正常・失敗・復旧・キャッシュテストが成功し、他能力を import しない。

- [x] 2.3 `src/app/model_evaluation/` に評価 CLI、checkpoint predictor、検査・可視化、結果集約を設計の配置表どおりに移す。評価 CLI は成果物の読込み前に `common/artifact_transaction.py` の `recover_artifact_transaction` を呼ぶ。学習時と同じモデル生成・スコア契約を `common/` から使い、未判定と再検査を維持する。対応: `AC-001`、`AC-002`、`AC-003`、既存 `REQ-009`〜`REQ-013`、設計「確定した配置」「処理フロー」「判断1・2」、`TC-001`〜`TC-003`、`TC-007`。完了条件: 中断後の学習成果物を復旧してから検査でき、評価・結果の既存正常・失敗・再検査テストが成功し、他能力を import しない。

## 3. 参照先と検証基盤

- [x] 3.1 `pyproject.toml` の5 entry point を各能力の CLI 関数へ更新し、`scripts/run_visual_inspection_smoke.py` とリポジトリ内の旧 `app.*` import・文字列 patch 参照を更新する。`tests/test_package_structure.py::test_console_script_entry_points` に5 CLI の entry point と `--help` の pytest 回帰検査を作成する。対応: `AC-002`、設計「判断3」「試験設計」、`TC-002`。完了条件: 5コマンド名と引数が維持され、全 entry point の import と `--help` が成功する。

- [x] 3.2 `tests/test_config.py`、`tests/test_preparation.py`、`tests/test_training.py`、`tests/test_evaluation.py`、`tests/test_results.py`、`tests/test_runtime.py`、`tests/test_platform_smoke.py`、`tests/conftest.py` の import と patch 先を新配置へ更新する。既存の書込み・置換失敗テストは `model_training/artifacts.py` の使用箇所を patch し、復旧関数・パス生成の参照先だけ `common/artifact_transaction.py` に更新する。`tests/test_evaluation.py::test_test_cli_recovers_interrupted_training_artifacts` を追加し、backup と中断 journal がある状態で `test` CLI が旧一式を復旧してから読み込むことを確認する。契約・異常・未判定・再実行の既存 assertion、成果物の読戻しを行う `tests/test_platform_smoke.py::test_workflow_records_runtime_contract`、実際のデバイス選択を行う `tests/test_runtime.py::test_select_device_falls_back_to_cpu` の pytest 検証を維持する。対応: `AC-003`、`AC-004`、既存 `REQ-001`〜`REQ-013`、設計「境界条件と失敗モード」「試験設計」、`TC-003`、`TC-005`、`TC-007`。完了条件: `uv run --locked pytest` が成功し、既存の検証項目が減っていない。

- [x] 3.3 `tests/test_runtime.py::test_run_preserves_exit_contract` に成功・入力不備・処理失敗を通す共通 CLI 実行処理の pytest 回帰テストを追加し、標準出力 JSON の項目、結果・警告・エラー、終了コード0・2・3を確認する。対応: `AC-002`、設計「インターフェースと失敗時の結果」「試験設計」、`TC-006`。完了条件: 対象テストが成功し、TC-002 の5 entry point・`--help` とタスク4.3の5 CLI 正常実行を合わせて CLI 契約を確認できる。

## 4. 配置案内・受け入れ

- [x] 4.1 `openspec/structure.md` に3仕様と実装パッケージ・`common/` の対応、能力間の依存方向、共有契約の置き方を記載する。`tests/test_package_structure.py::test_capability_import_boundaries` の pytest で禁じた import を検出し、文書とコードを照合する。対応: `AC-001`、設計「確定した配置」「判断1」「受け入れ検証」、`TC-001`。完了条件: 3仕様から実装を特定でき、依存境界テストが成功し、レビュー結果を `openspec/changes/organize-app-by-capability/evidence/acceptance.md` に記録できる。

- [x] 4.2 `uv run --locked pre-commit run --all-files`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change organize-app-by-capability --phase implementation`、`npx --no-install openspec validate organize-app-by-capability --strict` を実行して失敗を解消し、CLI・成果物・失敗経路をレビューする。対応: `AC-002`、`AC-003`、`AC-004`、設計「試験設計」「受け入れ検証」、`TC-002`〜`TC-004`、`TC-006`、`TC-007`。完了条件: 各コマンドが成功し、実行環境・日付・結果を `openspec/changes/organize-app-by-capability/evidence/acceptance.md` に記録する。

- [ ] 4.3 Ubuntu 24.04 LTS と Windows 11 の実機で、GPU 有効・無効の4条件に対し `scripts/run_visual_inspection_smoke.py` をそれぞれ異なる出力先で実行し、5 CLI の起動、引数、終了コード、標準出力の契約を確認する。失敗時の終了コードはタスク3.3の自動試験の確認範囲として区別する。対応: `AC-002`、設計「インターフェースと失敗時の結果」「受け入れ検証」、`TC-002`、`TC-006`。完了条件: 4条件の実機記録と OS・Python・依存版・コマンド・出力を `evidence/acceptance.md` に残し、未実施の間は未完了のままにする。

- [ ] 4.4 同じ実機4条件のスモーク結果で、準備 manifest、checkpoint、最良試行、検査結果の保存先・形式と `readable`、5 CLI 間の成果物の引き渡しを確認する。失敗・未判定・再実行はタスク3.2の自動試験の確認範囲として区別する。対応: `AC-003`、設計「データ契約と状態」「受け入れ検証」、`TC-003`、`TC-007`。完了条件: 実機成果物の読戻しと結果を `evidence/acceptance.md` に残し、未実施の間は未完了のままにする。

- [ ] 4.5 同じ実機4条件のスモーク結果で、`train`・`test` の `metadata.device.type` が GPU 有効時は `cuda`、GPU 無効時は `cpu` であることを照合する。GPU 無効化方法、実測デバイス、処理時間を記録し、期待と異なる場合は成功扱いしない。対応: `AC-004`、既存 `NREQ-001`、設計「試験設計」「受け入れ検証」、`TC-005`。完了条件: 両 OS の GPU/CPU 経路を `evidence/acceptance.md` に記録し、未実施の間は未完了のままにする。

- [x] 4.6 自動試験と品質検査、`design.md` の受け入れ状態と `evidence/acceptance.md`、README の「延期中の受け入れ確認」にある change 名・AC-ID・未完了タスク番号・確認内容をレビューする。`uv run --locked python scripts/check_openspec_traceability.py --change organize-app-by-capability --phase limited-archive` と `npx --no-install openspec validate organize-app-by-capability --strict` を実行する。対応: `AC-001`〜`AC-004`、設計「受け入れ検証」「網羅性確認」、`TC-001`〜`TC-007`。完了条件: 両検査が成功し、実機タスク4.3〜4.5のみ未完了、AC-002〜AC-004のみ未検証である。制限付きアーカイブは利用者へ残るリスクを示して明示的な了承を得た後に行う。
