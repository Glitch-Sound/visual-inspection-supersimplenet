# 検証記録

## 2026-10-23 自動試験・品質確認

- 環境: macOS 27.0.1、Python 3.13.15、torch 2.13.0、anomalib 2.6.2。CUDA は利用不可。
- `npm run check`: 成功。OpenSpec の全件厳密検証、ruff format / lint、pyright、pytest 299件、リポジトリ検査、進行中 change の implementation 段階トレーサビリティ検査が成功した。
- `npx --no-install openspec validate configure-synthetic-anomaly-generation --strict`: 成功。
- `uv run --locked pytest tests/test_model_adapter.py::test_synthetic_anomaly_large_scale_on_small_features tests/test_model_adapter.py::test_synthetic_anomaly_runs_in_real_training_model -q`: 2件成功。指数5の scale 32 を小さい特徴マップで生成し、実モデルの学習経路を通した。

## 2026-10-23 検証時の指摘に対する自動試験の補強

- `TC-001`: 設定ファイルから2グループを読み込み、3種類の範囲をグループごとに異なる固定値としてモデル生成器へ渡すことを確認した。学習試行から設定を渡す経路は `test_trial_runner_passes_synthetic_anomaly_and_seed` で確認した。
- `TC-005`、`TC-006`: 不正な範囲と型について実際の `train` CLI が終了コード2と入力不備を返し、既存の checkpoint と study を維持することを確認した。設定修正後の読込みも確認した。
- `TC-008`: 設定付きモデルの checkpoint を `CheckpointPredictor` が読み込み、擬似異常生成器を使わずに推論することを確認した。同じ predictor で検査結果 JSON と画像を書き出し、既存の主要フィールドと分割結果を確認した。
- `npm run check`: 成功。pytest 299件、ruff format / lint、pyright、OpenSpec 厳密検証、リポジトリ検査、implementation 段階トレーサビリティ検査が成功した。

`TC-001`〜`TC-008` の自動テストとローカル環境の生成器・推論契約を確認した。<br />
Ubuntu 24.04 LTS と Windows 11 の実画像、CPU と利用可能な GPU、全 CLI の再実行、成果物読戻しは未実施であり、`AC-001`〜`AC-005` は未検証のままである。<br />
本記録は検出性能と運用開始の承認を示さない。

## 2026-10-23 制限付きアーカイブ

- 利用者は `REQ-032`〜`REQ-035` の正式仕様への同期と、タスク4.2および `AC-001`〜`AC-005` を未検証として残す制限付きアーカイブを了承した。
- `uv run --locked python scripts/check_openspec_traceability.py --change archive/2026-10-23-configure-synthetic-anomaly-generation --phase limited-archive`: 成功。
- 正式仕様への同期後、`npx --no-install openspec validate --all --strict` は成功した。
