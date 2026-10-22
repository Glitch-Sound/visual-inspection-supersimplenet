## 1. 設定契約

- [x] 1.1 `src/app/common/config.py` に `synthetic_anomaly` の3範囲と推奨値を持つ設定モデルを追加し、`group_detail` の統合対象に加える。有限値、厳密な整数、真偽値、順序、上下限を検証し、入力不備で既存成果物を更新しない。対応: `REQ-032`、`REQ-034`、設計「データ契約と状態」「境界条件と失敗モード」、`TC-002`、`TC-005`、`TC-006`。完了条件: 全体・一部省略の既定値と不正入力の拒否を設定読込で確認できる。

## 2. 学習時の擬似異常生成

- [x] 2.1 `src/app/common/model_adapter.py` に Anomalib 2.6.2 の `AnomalyGenerator` 派生クラスを追加する。mask ごとの連続値と縦横指数を torch 乱数で選び、標準正規 noise に mask ごとの標準偏差を掛け、Perlin の scale を `2^n` で指定する。50% の適用判定、非重複、二値化、label 更新と特徴の合成を親クラスと照合する。対応: `REQ-033`、設計「処理フロー」「技術判断」、`TC-003`、`TC-004`。完了条件: 非固定・固定の範囲で生成器契約を自動試験でき、`common/` から個別能力への import を増やさない。
- [x] 2.2 `src/app/common/model_adapter.py` と `src/app/model_training/trainer.py` で対象グループ設定を学習モデルへ渡し、生成後に `model.model.anomaly_generator` を差し替える。既存の `execution.seed` を試行開始時の torch 乱数へ適用し、Optuna の探索候補や検査側のモデル生成には追加しない。対応: `REQ-032`、`REQ-033`、`REQ-035`、設計「処理フロー」「技術判断」「インターフェースと失敗時の結果」、`TC-001`、`TC-003`、`TC-007`、`TC-008`。完了条件: グループ別の生成器、seed、探索・推論からの分離を自動試験で確認できる。

## 3. 自動試験

- [x] 3.1 `tests/test_config.py::test_synthetic_anomaly_defaults`、`test_synthetic_anomaly_rejects_invalid_bounds`、`test_synthetic_anomaly_rejects_invalid_types` と `tests/test_model_adapter.py::test_synthetic_anomaly_uses_group_settings`、`test_synthetic_anomaly_samples_per_mask`、`test_synthetic_anomaly_preserves_generator_contract` の pytest テストを実装する。設定の省略、グループ分離、全端点の境界、固定値、mask 単位の抽選、同じ seed、50% 判定と Anomalib の更新契約を検証する。対応: `REQ-032`、`REQ-033`、`REQ-034`、設計「試験設計」、`TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`、`TC-006`。完了条件: 指定した6テストが pytest で成功する。
- [x] 3.2 `tests/test_training.py::test_synthetic_anomaly_is_not_search_parameter` と `tests/test_model_adapter.py::test_synthetic_anomaly_not_used_in_inference` を実装する。探索候補・結果に擬似異常条件がないこと、実モデルの推論で生成器を使用せず結果形式が変わらないことを検証する。対応: `REQ-035`、設計「試験設計」「インターフェースと失敗時の結果」、`TC-007`、`TC-008`。完了条件: 指定した2テストが pytest で成功する。

## 4. 案内・品質・受け入れ

- [x] 4.1 `config/part_XX.json` の各 `group_detail` に3項目の推奨値を追加し、他の設定値を変更しない。`README.md` の設定項目表と用語集に `synthetic_anomaly` を追加し、旧成果物を引き継がず `check` → `train-pre` → `train` → `test-pre` → `test` を再実行する手順を示す。対応: `REQ-032`、`REQ-035`、設計「データ契約と状態」「移行とロールバック」。完了条件: JSON の差分が追加項目のみで、案内と設定名・既定値が一致する。
- [ ] 4.2 `AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005` を Ubuntu 24.04 LTS と Windows 11 の実画像で確認し、CPU と利用可能な GPU、異なるグループ設定、無効な設定の拒否、全CLIの再実行、checkpoint・検査結果の読戻しを `openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md` に記録して design の「受け入れ検証」を更新する。対応: `AC-001`〜`AC-005`、設計「受け入れ検証」。完了条件: 各条件の実行日、OS、Python・依存版、使用デバイス、コマンド、結果、残る制約が記録され、検証済みの条件だけ状態を更新する。
- [x] 4.3 `npm run check`、`npx --no-install openspec validate configure-synthetic-anomaly-generation --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change configure-synthetic-anomaly-generation --phase implementation` を実行し、品質・試験収集を確認する。verify / archive 前には通常 `--phase complete`、実機受け入れだけを延期する場合は README への追跡記録と明示的な了承の後に `--phase limited-archive` を実行する。対応: `REQ-032`〜`REQ-035`、`AC-001`〜`AC-005`、設計「試験設計」「受け入れ検証」。完了条件: 実装・自動試験・品質確認の結果を記録し、該当工程の厳密検証とトレーサビリティ検査が成功する。
