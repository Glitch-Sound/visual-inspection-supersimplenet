# 自動試験・品質検査の記録

- 実施日: 2026-10-15、復旧修正後の再検証は2026-10-16
- 環境: macOS arm64、Python 3.13.15、pytest 9.1.1。依存版は `uv.lock`、OpenSpec はプロジェクトローカルの 1.13.1。
- `uv run --locked pytest`: 2026-10-15に264件成功。2026-10-16の`npm run check`内で267件成功。
- `npm run check`: 2026-10-16にOpenSpec厳密検証4件成功、ruff format/check成功、pyright 0 errors、pytest 267件成功、リポジトリ検査成功、進行中changeのトレーサビリティ検査成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change out-of-fold-threshold-and-refit --phase implementation`: `npm run check` 内で収集を含めて成功。
- `TC-001`〜`TC-013` は `tests/test_training.py` の指定関数で確認した。分割・スコア・全件投入・成果物整合はテストダブルと小規模フィクスチャによる契約確認を含む。
- `--restart`のプロセス中断を追加検証した。公開前の中断、3成果物更新中の中断、公開後の中断を模し、次のコマンド開始時に旧一式の復旧または公開済みの新一式の維持を確認した。
- 制約: Ubuntu 24.04 LTSとWindows 11の対象実機で、実画像・実重みを使う一連の学習、検査、成果物読戻しは未実施。対象OSでの受け入れ条件は未検証。
