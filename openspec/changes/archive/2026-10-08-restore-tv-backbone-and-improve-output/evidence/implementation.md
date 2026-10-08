# 実装・自動試験の記録

- 実施日: 2026-10-08
- 環境: macOS (Darwin 25.6.0、arm64)、Python 3.13.15、Anomalib 2.6.2、PyTorch 2.13.0、Optuna 5.0.0。
- `uv run --locked python scripts/check_openspec_traceability.py --change restore-tv-backbone-and-improve-output --phase design`: 成功。
- `npm run check`: OpenSpec全件の厳密検証、Ruff format/check、Pyright、pytest 220件、リポジトリ検査、トレーサビリティ実装段階検査が成功。
- `node_modules/.bin/openspec validate restore-tv-backbone-and-improve-output --strict`: 成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change restore-tv-backbone-and-improve-output --phase implementation`: 成功。参照するpytestテストを収集できた。
- `git diff --check`: 成功。

テストでは`tv_in1k`のモデル構築時の識別子と`pretrained=True`、再学習時の旧派生成果物削除、異常分割画像の左右画素と正常分割の不変、Optuna試行の開始表・終了状態・再開時の通知を確認した。実重みのダウンロードを伴う全型番の学習、Ubuntu 24.04 LTSとWindows 11での結果画像および端末表示は未実施であり、AC-001〜AC-004は未検証である。

## アーカイブ準備時の再確認

- 実施日: 2026-10-08
- 環境: macOS (Darwin 25.6.0、arm64)、Python 3.13.15。
- 表示テストに選択値、既存試行数、今回の試行数、最良試行の表題の確認を追加した。
- `npm run check`: 再実行して成功。pytest 220件、Ruff、Pyright、リポジトリ検査、OpenSpec厳密検証、トレーサビリティ実装段階検査が成功した。
- `npx --no-install openspec validate restore-tv-backbone-and-improve-output --strict`: 成功。
- 対象OSと実画像・全型番のデータはこのmacOS環境にないため、AC-001〜AC-004の実機確認は未実施のままにする。
- 利用者はAC-001〜AC-004を未検証として残すこと、正式仕様の同期、制限付きアーカイブを明示的に了承した。
- 正式仕様へ`NREQ-004`を追加し、`REQ-020`と`REQ-010`を差分仕様に合わせた。`openspec validate --specs`は3件成功した。
- 利用者了承後の`uv run --locked python scripts/check_openspec_traceability.py --change restore-tv-backbone-and-improve-output --phase limited-archive`は成功した。未完了は延期対象の5.1〜5.4だけである。
- 正式仕様の同期後に`npm run check`を再実行し、OpenSpec全件、Ruff、Pyright、pytest 220件、リポジトリ検査、実装段階のトレーサビリティ検査が成功した。
