## 1. 対象環境と依存関係

- [x] 1.1 `pyproject.toml`のCUDA wheel条件をLinuxだけにし、`uv.lock`を再生成する。対応: `NREQ-001`、設計「技術判断」、`TC-001`。完了条件: Ubuntu向け依存が解決し、Windows向けwheelがlockfileに残らない。
- [x] 1.2 `README.md`の動作環境、実機スモーク、延期中の確認内容と現行仕様をUbuntuのみへ更新する。対応: `NREQ-001`、設計「業務フローと責務」、`TC-001`。完了条件: 現行の運用案内にWindows向け要件が残らない。

## 2. 専用分岐と自動試験

- [x] 2.1 `src/app/common/config.py`、`contracts.py`、`tests/test_package_structure.py`からWindows専用のパス・実行ファイル分岐を除き、`tests/test_check_openspec_traceability.py`の試験データを対象OS非依存にする。対応: `NREQ-001`、設計「技術判断」、`TC-001`、`TC-002`。完了条件: 既存のCLI・CPU切替・入力検証テストが成功する。

## 3. 検証

- [x] 3.1 `tests/test_runtime.py::test_nreq_002_s01`の`TC-001`と`tests/test_runtime.py::test_req_009_s02`の`TC-002`をpytestで実行し、`npm run check`と現行文書・実装のWindows専用記述検索で`AC-002`を確認する。対応: `NREQ-001`、`AC-002`、設計「試験設計」「受け入れ検証」。完了条件: 品質検査成功と証跡記録、AC-002の検証済み。
- [ ] 3.2 Ubuntu 24.04 LTS x86-64で`uv sync --locked`とCPU・利用可能なGPUの全5 CLIスモーク、成果物読戻しを実施して`AC-001`の証跡を残す。対応: `NREQ-001`、`AC-001`、設計「受け入れ検証」、`TC-001`、`TC-002`。完了条件: 実機の条件・結果を記録し、AC-001を検証済みにする。実機が利用できなければ未完了のままREADMEへ延期を記録する。
