# comparable-heatmap-scale 検証記録

## 自動検査

- 実施日: 2026-10-08 JST
- 環境: macOS (Darwin 25.6.0 arm64)、Python 3.13.15。対象の Ubuntu 24.04 LTS・Windows 11 ではない。
- `uv run --locked pytest tests/test_config.py tests/test_evaluation.py tests/test_results.py tests/test_platform_smoke.py -q`: 81 件成功 (境界値テスト追加前)。
- `npm run check`: OpenSpec 全体の strict validate、Ruff format/lint、Pyright、pytest 212 件、リポジトリ検査、全 change の implementation トレーサビリティが成功 (境界値テスト追加前)。
- `uv run --locked pytest tests/test_evaluation.py::test_heatmap_uses_shared_range_across_images -q`: 境界値テスト追加後、1 件成功。
- 最終の `npm run check`: 境界値テスト・README・design 更新後に再実行し、全工程成功、pytest 212 件成功、Pyright 0 エラー・0 警告。
- 分割エラー結果への範囲記録を追加確認した後、`uv run --locked pytest tests/test_evaluation.py::test_evaluation_records_heatmap_range_in_results -q`、`uv run --locked ruff check tests/test_evaluation.py`、`uv run --locked ruff format --check tests/test_evaluation.py` が成功。
- `npx --no-install openspec validate comparable-heatmap-scale --strict`: 成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change comparable-heatmap-scale`: 設計段階、成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change comparable-heatmap-scale --phase implementation`: 参照テスト収集、成功。
- `git diff --check`: 成功。
- アーカイブ前の `npm run check`: 主仕様同期と受け入れタスク分割後に再実行し、pytest 212 件を含む全工程が成功。
- `npx --no-install openspec validate --specs`: 同期後の主仕様 3 件が成功。REQ-019、REQ-010、REQ-012 の各ブロックは変更仕様と一致。
- `npx --no-install openspec validate comparable-heatmap-scale --strict`: アーカイブ前に再実行し成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change comparable-heatmap-scale --phase limited-archive`: README の AC-001〜004 引き継ぎと未完了タスク 4.2〜4.5 を確認して成功。

TC-001〜TC-010 は上記 pytest に含まれる。<br />
正常画像の画素一致、異常画像の表示範囲への線形写像と端色、スコア・閾値・判定の独立性、結果 JSON の保存・読戻し・不正値拒否、危険な manifest の推論前拒否を自動検査した。

## 対象環境の受け入れ確認

AC-001〜AC-004 は未検証。<br />
タスク 4.2〜4.5 の Ubuntu 24.04 LTS・Windows 11、運用で同一性を確認した学習済みモデルと実画像を使う確認は、この macOS 環境では実施できない。<br />
各 OS でモデル確認方法、使用した表示範囲、結果画像・JSON、実行コマンド、日付、制約を記録する。<br />
本記録の自動試験成功は、対象 OS での受け入れや運用開始の承認を意味しない。
利用者は 2026-10-08 に README への引き継ぎを指示し、問題がなければアーカイブすることを明示した。
