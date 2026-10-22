# 受け入れ検証記録

## 自動検証

- 実施日: 2026-10-22 (Asia/Tokyo)。
- 環境: macOS Darwin 27.0.0、arm64、Python 3.13.15。対象OSの Ubuntu 24.04 LTS と Windows 11 ではない。
- `uv run --locked pytest -q --tb=short`: 初回実装で233件成功。
- `npm run check`: OpenSpec 全4件の厳格検証、Ruff、Pyright、pytest 234件、リポジトリ検査、全changeの実装段階トレーサビリティ検査が成功。追加した検査CLIの入力不備終了コードとグループ間の位置合わせ結果も含む。
- `npm run check` (最終確認): 同じ品質検査とpytest 235件が成功。
- `npm run check` (制限付きアーカイブ準備): 同じ品質検査とpytest 236件が成功。複数ACを一つの実機確認タスクへ対応付ける検査も含む。
- `uv run --locked pytest tests/test_evaluation.py::test_req_023_s03_cli_input_error -q --tb=short`: checkpointと最良試行ファイル欠落の2条件が成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change drop-legacy-and-recovery-handling --phase implementation`: 成功。設計の TC-001～TC-056 に対応する参照テストを収集できた。
- `npx --no-install openspec validate drop-legacy-and-recovery-handling --strict`: 成功。削除した Scenario を正本仕様にも反映した状態で検証した。
- `git diff --check`: 成功。

## AC別の状態

| AC-ID | 自動検証で確認した内容 | 残る検証 | 状態 |
| --- | --- | --- | --- |
| AC-001 | 準備・検査の公開前失敗、旧成果物保持、残存一時領域の削除をテストした | 対象OSで四CLIの実行と中断を確認する | 未検証 |
| AC-002 | `train` の新規探索と全グループ途中失敗時の部分成功をテストした | 対象OSの実モデルで再探索と部分成功を確認する | 未検証 |
| AC-003 | 学習成果物公開後の閾値書戻し、他設定の保持、書戻し失敗をテストした | 対象OSの実モデルと設定で確認する | 未検証 |
| AC-004 | 準備・checkpoint・最良試行・結果参照の欠落と不整合の拒否をテストした | 対象OSで中断時の欠落と再実行を確認する | 未検証 |
| AC-005 | 型番排他、シンボリックリンク拒否、詳細設定の拒否と文書を確認した | 対象OSで排他・パス境界・一連の工程を確認する | 未検証 |

対象OSの実機検証はタスク3.3として残る。自動試験の成功は対象OSでの受け入れ完了を意味しない。
