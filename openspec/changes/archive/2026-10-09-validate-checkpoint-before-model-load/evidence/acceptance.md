# 受け入れ検証記録

- 実施日: 2026-10-08 (Asia/Tokyo)。
- 環境: macOS Darwin 25.6.0 arm64、Python 3.13.15、pytest 9.1.1。<br />
  実行環境の依存版は anomalib 2.6.2、torch 2.13.0、torchvision 0.28.0、opencv-python-headless 5.0.0.93、optuna 5.0.0。
- 手順: `uv run --locked pytest -q tests/test_evaluation.py`、`npm run check`、`npx --no-install openspec validate validate-checkpoint-before-model-load --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change validate-checkpoint-before-model-load --phase complete`。

| 受け入れID | 結果 | 根拠 |
| --- | --- | --- |
| AC-001 | 検証済み | `test_test_cli_rejects_checkpoint_contract_before_model_construction` でメタデータ欠落と閾値不一致を入力し、モデル構築なし、理由、終了コード2を確認した。 |
| AC-002 | 検証済み | `test_test_cli_validates_checkpoint_before_model_construction` で照合済みメタデータの引渡し、終了JSONと終了コード0を確認した。既存評価テストと `npm run check` の全223テストが成功した。 |

制約: モデル構築はテストダブルを使用した。<br />
この記録は CLI の契約照合順序と既存自動試験の回帰を対象とし、対象OSで実重みを使う運用受け入れを示さない。
