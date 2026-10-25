# 自動試験・品質確認の証跡

- 実行日: 2026-10-25 (Asia/Tokyo)
- 環境: Apple silicon macOS 27.0.1 (arm64)、Python 3.13.15、pytest 9.1.1。
- 対象: `polish-review-leftobers` の TC-001〜TC-009。実画像による全工程と Ubuntu 24.04 LTS での確認は含まない。

| コマンド | 結果 | 確認範囲 |
| --- | --- | --- |
| `uv run --locked pytest tests/test_config.py tests/test_training.py -q` | 212件成功 | 設定・パス・学習の既存試験と追加した境界・失敗試験 |
| `npx --no-install openspec validate polish-review-leftobers --strict` | 成功 | change の成果物形式と差分仕様 |
| `uv run --locked python scripts/check_openspec_traceability.py --change polish-review-leftobers --phase implementation` | 成功 | 要件・Scenario・TC・タスクの対応と pytest 収集 |
| `npm run check` | 成功。pytest 435件成功 | 全spec厳密検証、format、lint、pyright (0件)、全pytest、リポジトリ検査、進行中changeの実装段階トレーサビリティ |
| `git diff --check` | 成功 | 変更済み追跡ファイルの空白エラーなし |

TC-006は5コマンドへ巨大整数を与えた時の終了コード2、IDと項目の表示、既存成果物の不変を確認した。<br />
TC-007は設定・準備・成果物のリンク拒否とパス表示、リンク先と既存成果物の不変を確認した。<br />
TC-008・TC-009は実際の Optuna ストレージ接続と、探索・公開の失敗注入を組み合わせ、接続終了が一時領域削除に先行すること、旧成果物の保全と再実行を確認した。<br />
TC-001〜TC-005は既存の設定試験で確認した。

制約: 自動試験には軽量の試験データと一部のテストダブルを使用した。<br />
Ubuntu 24.04 LTS の実行環境、および対象型番の実画像データはこの作業環境にないため、AC-001〜AC-004の対象環境での受け入れは未検証である。
