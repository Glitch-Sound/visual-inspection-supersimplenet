# 自動試験と品質検査

- 実施日: 2026-10-16
- 環境: macOS 26.6.2 arm64、Python 3.13.15、pytest 9.1.1、CUDAなし。
- `uv run --locked pytest tests/test_training.py -q`: 63件成功。<br />
  TC-001〜TC-003はテストダブル上でモデル生成・学習・保存・推論中の決定論設定、学習・推論失敗時の復元、同seedの2回の探索条件・目的値・最良試行を確認した。<br />
  TC-004〜TC-012は閾値計算、保存契約、失敗時保全と既存の回帰を確認した。
- `npm run check`: OpenSpec全件厳密検証、ruff format/check、pyright、pytest 329件、リポジトリ検査、全進行中changeのimplementationトレーサビリティ検査が成功。
- `npx --no-install openspec validate fix-gpu-determinism-and-refit-threshold --strict`: 成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change fix-gpu-determinism-and-refit-threshold --phase implementation`: 成功。参照pytestの収集も成功。
- `git diff --check`: 成功。

実CUDA演算、Ubuntu 24.04 LTSでの一連の学習、実画像・実checkpointによる再計算は未実施。<br />
AC-001〜AC-006の状態は「未検証」のままとする。
