## 1. 入力・成果物名の検証

- [x] 1.1 `src/app/common/config.py` の基準画像名検証から Windows ドライブ名判定と不要な import を削除し、空名、`.`、`..`、区切り文字、POSIX 絶対パスの拒否を維持する。対応: `REQ-001`、設計「技術判断: パス検証」「インターフェースと失敗時の結果」、`TC-003`。完了条件: 不正な `base` は処理開始前に入力不備となり、通常名は受理される。
- [x] 1.2 `src/app/common/contracts.py` の共通ファイル名検証から Windows ドライブ名判定と不要な import を削除し、POSIX の拒否条件を維持する。対応: `REQ-001`、設計「技術判断: パス検証」「データ契約と状態」、`TC-003`。完了条件: 準備・検査成果物名の不正値が拒否され、ルート外を読み書きしない。

## 2. 対象環境と案内の更新

- [x] 2.1 `tests/test_package_structure.py` の `win32` 分岐を削除し、`pyproject.toml` の torch・torchvision の CUDA index マーカーを Linux のみに変更する。uv の解決対象を Linux と Apple silicon macOS に限定して `uv lock` で `uv.lock` を更新する。対応: `NREQ-001`、設計「技術判断: 依存取得と対象環境」、`TC-006`。完了条件: Windows 用分岐と解決結果が消え、対象環境のロック済み依存を解決できる。
- [x] 2.2 `README.md`、正式仕様の `NREQ-001` と関連試験方針、進行中 change の対象環境記述を Ubuntu 24.04 LTS (ネイティブまたは WSL2) と Apple silicon macOS に揃える。README の延期中の受け入れ確認は AC-ID と未検証状態を維持し、Windows 専用項目は現行対象外と明記する。旧成果物を引き継がず全工程を再実行する手順も確認する。対応: `NREQ-001`、`REQ-001`、`AC-004`、設計「技術判断: 過去の検証記録」「移行とロールバック」、`TC-006`。完了条件: 現行案内に Windows 11 を対象とする記述や曖昧な「両OS」が残らず、履歴上の未実施を検証済みとしない。

## 3. 自動試験と対象環境の受け入れ

- [x] 3.1 `tests/test_preparation.py::test_group_req_001_s03` に POSIX 絶対パス、親参照、区切り文字の拒否を追加し、`tests/test_config.py::test_safe_artifact_filename_posix_path_rejected` に共通契約の拒否と通常名の受理を追加する。既存の `test_group_req_001_s01`、`s02`、`s04`、`s05` と `tests/test_platform_smoke.py` の2試験も pytest で実行する。対応: `REQ-001`、`NREQ-001`、設計「試験設計」、`TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`、`TC-006`、`TC-007`。完了条件: 全 TC-ID の自動試験が収集・成功し、テストダブルの範囲を証跡に記録できる。
- [ ] 3.2 Ubuntu 24.04 LTS (ネイティブまたは WSL2) と Apple silicon macOS で `uv sync --locked`、`npm run check` を実行し、OS、Python・依存版、結果を `openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md` に記録して design の状態を更新する。対応: `NREQ-001`、`AC-001`、設計「受け入れ検証」、`TC-006`。完了条件: 両対象環境で成功し、証跡と残る検証「なし」が揃う。
- [ ] 3.3 両対象環境で実画像を使い `check`、`train-pre`、`train`、`test-pre`、`test` を全再実行する。CPU と利用可能な CUDA GPU、GPU 無効化、入力不備、成果物読戻しを確認し、環境・手順・結果を `openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md` に記録して design の状態を更新する。対応: `REQ-001`、`NREQ-001`、`AC-002`、`AC-003`、設計「受け入れ検証」、`TC-001`〜`TC-007`。完了条件: 対象環境の全工程と拒否・復旧が確認され、証跡と残る検証「なし」が揃う。
- [x] 3.4 README、正式仕様、進行中 change の現行対象環境と延期表をレビューし、`AC-004` の結果を証跡に記録する。`npx --no-install openspec validate drop-windows-support --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change drop-windows-support --phase implementation` を実行する。verify / archive 前には通常 `--phase complete`、実機確認だけを延期する場合は README に change 名・AC-ID・未完了タスク番号を記録し、利用者の明示的了承後に `--phase limited-archive` を実行する。対応: `REQ-001`、`NREQ-001`、`AC-004`、設計「受け入れ検証」「網羅性確認」、全 `TC-ID`。完了条件: 品質検査と厳密検証が成功し、受け入れ状態と証跡が実施結果に一致する。
