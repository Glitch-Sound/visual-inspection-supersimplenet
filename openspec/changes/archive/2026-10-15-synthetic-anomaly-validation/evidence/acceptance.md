# 擬似欠陥評価の検証記録

## 自動試験・品質確認

- 実施日: 2026-10-15。
- 環境: macOS 26.6.2 (Build 25G83)、Python 3.13.15、`uv --locked` の依存版。
- `uv run --locked pytest`: `npm run check` 内で251件成功。画像生成、設定検証、探索目的・方向、保存契約、既存機能を確認した。微小強度と小画像の差分、生成失敗を1件の失敗試行として記録して旧成果物を保持する動作、目的名表示、擬似画像のグループ単位生成も確認した。
- `npm run check`: OpenSpec厳密検証、format、lint、pyright、pytest 251件、リポジトリ検査、進行中changeの実装段階トレーサビリティ検査が成功した。
- 延期確認のトレーサビリティ検査では、同じ未完了タスクへ複数のACを対応付けるケースと、同一ACの重複を拒否するケースを確認した。
- `uv run --locked python scripts/check_openspec_traceability.py --change synthetic-anomaly-validation --phase implementation`: 全参照テストを収集でき、対応検査が成功した。
- `npx --no-install openspec validate synthetic-anomaly-validation --strict`: 成功した。

試験ダブルを用いた探索試験は実モデルの検出性能を確認しない。<br />
擬似画像の再現と原本不変は小さなテスト画像で確認した。<br />
Ubuntu 24.04 LTS と Windows 11 の対象実機による AC-001〜AC-005 は未検証である。
