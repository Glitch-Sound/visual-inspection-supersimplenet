# 受け入れ検証記録

- 実施日: 2026-10-07
- 環境: macOS 26.6.2 arm64、Python 3.13.15。Ubuntu実機での全学習は未実施。
- 品質確認: `npm run check` 成功。OpenSpec厳密検証、ruff format/check、pyright、pytest 154件、リポジトリ検査、トレーサビリティ検査が成功。
- 参照試験収集: `uv run --locked python scripts/check_openspec_traceability.py --change align-model-training-template --phase implementation` 成功。
- 完了検査: `npx --no-install openspec validate align-model-training-template --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change align-model-training-template --phase complete` 成功。

## AC-001

`uv run --locked pytest tests/test_config.py::test_training_template_matches_defaults tests/test_training.py::test_search_selects_lowest_validation_percentile -q` を実行して成功した。
ひな形とテスト用設定のエポック候補100・200・300、warmup40、試行10を確認した。
実OptunaのMedianPrunerへの5試行・40 epoch・10 epoch間隔の引渡しと、軽量runnerによる10試行の記録を確認した。
全10試行を実モデルで学習する対象OS試験は含まない。

## AC-002

`uv run --locked pytest tests/test_training.py::test_blur_template_default_and_opt_in tests/test_training.py::test_validation_pipeline_disables_augmentation -q` を実行して成功した。
blurの初期無効、明示的に有効化した時の学習入力の変化、検証入力の不変を確認した。

## AC-003

`git diff -- config/part_XX.json` で利用者が変更した4値を維持していることを確認した。
差分仕様では `REQ-005` と `REQ-006` の該当値を更新した。
`git status --short` で設定ひな形、正式仕様、設定モデル、テスト用設定、テスト、当changeの成果物以外に変更がないことを確認した。
既存の学習成果物への変更はない。
正式仕様の `REQ-005` と `REQ-006` を差分仕様と一致させ、`npx --no-install openspec validate --specs` で確認した。
