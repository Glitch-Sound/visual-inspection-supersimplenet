# 検証記録 (2026-10-16)

## 実施環境

- 開発環境: macOS (Darwin)、Python 3.13.15。
- 対象環境の Ubuntu 24.04 LTS と対象型番の実画像はこの作業環境にない。
- この記録は自動試験と設計検査の結果であり、AC-001〜AC-005 の対象環境での受け入れ確認は未検証である。

## 自動試験と品質確認

| 実行内容 | 結果 | 範囲・制約 |
| --- | --- | --- |
| `uv run --locked pytest -q tests/test_synthetic_validation.py tests/test_training.py tests/test_config.py` | 111件成功 | 擬似画像、探索、設定の単体・統合試験。対象実画像・対象OSの確認ではない |
| `npm run check` | 342件成功。OpenSpec、format、lint、pyright、リポジトリ検査、実装段階のトレーサビリティも成功 | 全自動ゲート。実機受け入れを含まない |
| `uv run --locked python scripts/check_openspec_traceability.py --change tune-synthetic-validation --phase implementation` | 成功 | 参照テストの収集と対応。試験内容の妥当性や実機結果を保証しない |
| `npx --no-install openspec validate tune-synthetic-validation --strict` | 成功 | 計画成果物の形式・構造 |

## 対象環境で残る確認

- AC-001 / タスク4.1: Ubuntu 24.04 LTSの対象実画像で4種類、画素・強度範囲、複数枚、同seed再現、原本不変を確認する。
- AC-002〜AC-004 / タスク4.2: 同点選択、上限件数・警告、旧設定互換、再開拒否と旧成果物保持を実学習と結果JSONで確認する。
- AC-005 / タスク4.3: 対象型番の残り誤差と実画像から雛形の範囲および平行移動・回転の拡張強度を評価する。

擬似 AUROC と現在の自動試験結果だけでは、実異常の検出性能や本番利用を承認できない。
