# 自動検証の証跡

- 実施日: 2026-10-16。
- 環境: macOS (darwin)、Python 3.13.15、pytest 9.1.1。
- コマンド: `npm run check`。
- 結果: OpenSpec厳密検証、ruff format/check、pyright、pytest 319件、リポジトリ検査、`--phase implementation` のトレーサビリティ検査が成功。
- 範囲: `test-pre --group` のCLI記録、分割の部分更新、manifest統合、不明ID・指紋不一致時の既存結果保持、単独準備後の単独・全件検査をテストダブルとローカル画像で確認。<br />
  AC-004 は保持旧分割を伴う位置合わせ失敗後にpredictorが呼ばれず、元画像判定が `undetermined`、`recapture_required=true` となることを確認。
- 残る検証: Ubuntu 24.04 LTS・Windows 11の対象環境で、実画像を用いた AC-001〜AC-003 の確認。
