# 受け入れ検証記録

- 実施日: 2026-10-09 (Asia/Tokyo)。
- 環境: macOS (darwin)、Python 3.13.15、pytest 9.1.1。
- 対象: `validate-prepared-manifest-inputs` の `AC-001`、`AC-002`、`AC-003`。

| 条件 | 実施方法と結果 | 制約 |
| --- | --- | --- |
| AC-001 | `tests/test_training.py::test_train_rejects_invalid_prepared_manifest`、`tests/test_evaluation.py::test_evaluation_rejects_invalid_manifest_before_prediction`、`tests/test_evaluation.py::test_test_cli_restart_preserves_results_for_invalid_manifest` で設定外IDと画像名不一致を拒否し、学習・モデル構築・推論へ進まないことを確認した。`npm run check` に含まれる。 | 並行したファイル差替えは対象外。 |
| AC-002 | `tests/test_training.py::test_train_rejects_symlinked_prepared_input`、`tests/test_evaluation.py::test_evaluation_rejects_symlinked_prepared_input`、`test_test_cli_restart_preserves_results_for_invalid_manifest` でmanifest・画像・準備フォルダのリンクを拒否し、既存成果物と外部ファイルの内容を保持することを確認した。`npm run check` に含まれる。 | macOSで確認。Windowsでのリンク作成権限の差異は既存の対象OS受け入れ確認に含める。 |
| AC-003 | `tests/test_training.py::test_train_cli_accepts_valid_prepared_images` で実ファイルを持つ正常manifestから `train` CLIが集合分離・探索への引き渡しと成功終了まで進むことを確認した。既存の検査結果保存テストも確認した。`npm run check` で238テスト、ruff、pyright、リポジトリ検査、OpenSpec検証、実装段階のトレーサビリティ検査が成功した。 | 学習器はテストダブル。実重みを使う対象OSの総合スモーク試験は既存の延期項目で管理する。 |

追加検証: `npx --no-install openspec validate validate-prepared-manifest-inputs --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change validate-prepared-manifest-inputs --phase implementation` が成功した。
