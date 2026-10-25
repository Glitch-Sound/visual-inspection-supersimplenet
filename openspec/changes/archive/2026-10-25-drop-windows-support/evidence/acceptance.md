# 実装・受け入れ確認記録

## 実施環境

- 実施日: 2026-10-25
- OS: macOS 27.0.1、Apple silicon arm64
- Python: 3.13.15
- 主要依存: torch 2.13.0、torchvision 0.28.0、anomalib 2.6.2
- 使用デバイス: ローカル自動試験は CPU。CUDA は利用不可

## 実施結果

- `uv lock`: 126パッケージを解決。解決対象は Linux と Apple silicon macOS。Windows 固有の解決結果は除去した。
- `uv sync --locked`: macOS arm64 で成功。
- `uv run --locked pytest tests/test_preparation.py::test_group_req_001_s01 tests/test_preparation.py::test_group_req_001_s02 tests/test_preparation.py::test_group_req_001_s03 tests/test_preparation.py::test_group_req_001_s04 tests/test_preparation.py::test_group_req_001_s05 tests/test_config.py::test_safe_artifact_filename_posix_path_rejected tests/test_platform_smoke.py tests/test_package_structure.py -q`: 20件成功。固定画像とテストダブルを用いた契約確認であり、実画像による全 CLI の確認ではない。
- `npm run check`: OpenSpec 厳密検証、format、lint、型検査、pytest、リポジトリ検査、実装段階のトレーサビリティ検査が成功。pytest は424件成功、55件の警告。警告は主に依存ライブラリの非推奨通知である。
- README の延期表は既存の69組の change・AC-ID と「未検証」状態を維持した。旧対象環境専用の行は現行対象外の履歴と明記した。README、正式仕様、実装コード、依存設定・ロックファイルに Windows 11、`win32`、`両OS` の現行対象記述がないことを確認した。

## 未検証の条件

- `AC-001`: macOS arm64 の固定依存と既存自動試験は確認した。Ubuntu 24.04 LTS (ネイティブまたは WSL2) では未実施。タスク3.2を未完了とする。
- `AC-002`: 対象環境の実画像による `check`、`train-pre`、`train`、`test-pre`、`test` の全再実行と新成果物の読戻しは未実施。リポジトリ内に運用画像がなく、Ubuntu 実行環境も確認できなかった。タスク3.3を未完了とする。
- `AC-003`: POSIX 絶対パス、親参照、区切り文字、通常名の自動試験は確認した。対象環境の実 CLI による確認は未実施。タスク3.3を未完了とする。
- `AC-004`: 現行案内、正式仕様、延期表の文書レビューは実施済み。アーカイブ済み change の過去の記録は保持した。

Docker の利用可否を確認しようとしたが、サンドボックスからの Docker API 接続が拒否され、権限昇格の要求も拒否された。Ubuntu の試験結果として扱わない。
