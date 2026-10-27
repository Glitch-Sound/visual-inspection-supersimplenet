# 実装段階の検証記録

- 実施日: 2026-10-27 (Asia/Tokyo)。
- 環境: Apple silicon macOS、Python 3.13.15、Node.js / npm はリポジトリの既存環境を使用した。
- `uv run --locked test-pre --help`: 終了コード0。`--model` と `--group` を表示した。
- `npx --no-install openspec validate add-test-pre-group --strict`: 成功した。
- `uv run --locked python scripts/check_openspec_traceability.py --change add-test-pre-group --phase implementation`: 成功した。
- `npm run check`: OpenSpec、format、lint、pyright、451件のpytest、リポジトリ検査、全進行中changeの対応検査が成功した。
- `TC-003`・`TC-004`: 単独 `test-pre --group 1` の失敗時に、標準エラーと実行記録へグループIDと画像名を表示し、旧準備成果物を保持した。範囲外では分割IDも確認した。
- `TC-014`: 対象グループのmanifest欠落と指紋不一致の両方で、再準備案内を出し、全対象グループの旧検査結果を保持した。
- 固定画像とテストダブルによる14件の新規シナリオ試験を含む。実際の運用画像、Ubuntu 24.04 LTS、実モデルでの全工程は未確認である。
