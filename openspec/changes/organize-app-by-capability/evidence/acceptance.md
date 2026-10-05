# 受け入れ証跡（進行中）

## 2026-10-05 開発環境

- 環境: macOS 26.6.2 arm64、Python 3.13.15、torch 2.13.0、anomalib 2.6.2、Optuna 5.0.0。
- `uv run --locked pytest -q`: 121件成功。TC-001〜TC-007 と既存の設定・準備・探索・成果物復旧・判定・再実行テストを含む。
- `uv run --locked pyright`: エラー0件。
- `uv run --locked ruff check src tests scripts`: 成功。
- `uv run --locked pre-commit run --all-files`: repository checks、Ruff lint、Ruff format 成功。
- `npm run check`: OpenSpec 全件 strict validate、Ruff、pyright、121件の pytest、repository check、OpenSpec 実装段階トレーサビリティ検査に成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change organize-app-by-capability --phase implementation`: 成功。TC-001〜TC-007 の単一 pytest 参照を収集可能。
- `npx --no-install openspec validate organize-app-by-capability --strict`: 成功。

## レビュー結果

| 条件 | 開発環境で確認した範囲 | 残る検証 |
| --- | --- | --- |
| AC-001 | `openspec/structure.md` の3仕様と4実装領域の対応を確認。TC-001 が能力間と `common` から能力への import を検査。旧12モジュールのトップレベル定義126件が新配置に存在することを照合 | なし |
| AC-002 | TC-002 が5 console script の登録先と `--help`、`--model`、`--restart` の有無を検査。TC-006 が出力 JSON、結果・警告・エラー、終了コード0/2/3を検査 | Ubuntu / Windows の実機5 CLI 正常実行と出力記録 |
| AC-003 | TC-003 と既存テストが成果物の読戻し、失敗・未判定・再実行を検査。TC-007 が中断 journal による checkpoint・設定・最良試行の評価前復旧を検査 | Ubuntu / Windows の実機成果物の読戻し |
| AC-004 | TC-004、TC-005 と統合品質検査が成功。GPU 利用不可・初期化失敗時の CPU 選択を単体検査 | Ubuntu 24.04 LTS / Windows 11 の GPU 有効・無効、計4条件の実機確認 |

## 未実施の実機受け入れ

タスク4.3の対象環境はこの作業環境にないため未実施。4条件それぞれで `scripts/run_visual_inspection_smoke.py` を異なる出力先に実行し、5 CLI の終了コード、`metadata_valid`、全成果物の `readable`、`train`・`test` の実測 `metadata.device.type`、GPU 無効化方法、OS・Python・依存版・処理時間を記録する。期待デバイスとの不一致は成功扱いしない。タスク4.3・4.4を未完了とし、change を進行中に保つ。
