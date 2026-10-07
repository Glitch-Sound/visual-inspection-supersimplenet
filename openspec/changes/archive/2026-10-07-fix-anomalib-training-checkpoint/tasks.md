## 1. 学習・検査境界の修正

- [x] 1.1 `src/app/model_training/trainer.py` の検証集合の渡し方を `same_as_test` にし、再分割比率を削除する。対応: `REQ-014`、設計「検証集合の利用」、`TC-001`。完了条件: 検証集合の全件を渡す設定となる。
- [x] 1.2 `src/app/common/model_adapter.py` のモデルクラスをモジュール直下に移し、倍率をインスタンスに保持する。対応: `REQ-015`、設計「checkpoint保存可能なモデル」、`TC-002`。完了条件: pickle可能で、両学習率の倍率を維持する。
- [x] 1.3 `src/app/model_evaluation/predictor.py` のメタデータ読込をアプリ生成checkpointに対応させる。対応: `REQ-016`、設計「checkpointメタデータ読込」、`TC-003`、`TC-004`。完了条件: PreProcessor入りcheckpointを読み、欠落時の拒否を維持する。

## 2. 自動試験と品質確認

- [x] 2.1 `tests/test_training.py::test_trial_runner_uses_all_validation_images` でFolderへの集合引き渡しを確認する。対応: `REQ-014` / `REQ-014-S01` / `TC-001`。完了条件: 該当pytestが成功する。
- [x] 2.2 `tests/test_training.py::test_tunable_model_is_pickleable_and_uses_trial_multiplier` と `tests/test_training.py::test_tunable_model_saves_lightning_checkpoint` でモデルのpickle可能性・倍率と実Lightningによるcheckpoint保存を確認する。対応: `REQ-015` / `REQ-015-S01` / `TC-002`。完了条件: 両pytestが成功する。
- [x] 2.3 `tests/test_evaluation.py::test_load_checkpoint_metadata_with_preprocessor`、`tests/test_evaluation.py::test_evaluation_starts_with_preprocessor_checkpoint`、`tests/test_evaluation.py::test_load_checkpoint_metadata_rejects_missing_metadata` でPreProcessor入りcheckpointのメタデータ読込、検査開始、欠落時拒否を確認する。対応: `REQ-016` / `REQ-016-S01` / `REQ-016-S02` / `TC-003` / `TC-004`。完了条件: 3件のpytestが成功する。
- [x] 2.4 `npm run check` と `--phase implementation` のトレーサビリティ検査を実行し、結果を記録する。対応: 全要件、全TC。完了条件: 自動品質検査が成功する。

## 3. 対象OSでの受け入れ

- [ ] 3.1 Ubuntu 24.04 LTSで学習から検査を実行し、元画像単位で分けた検証画像が追加分割されず全件利用されることを確認する。対応: `AC-001`、設計「受け入れ検証」。完了条件: 対象環境、入力集合、検証結果を証跡に記録する。
- [ ] 3.2 Ubuntu 24.04 LTSで学習から検査を実行し、試行ごとの学習率倍率を維持してcheckpointを保存できることを確認する。対応: `AC-002`、設計「受け入れ検証」。完了条件: 対象環境、倍率、checkpoint保存結果を証跡に記録する。
- [ ] 3.3 Ubuntu 24.04 LTSで学習から検査を実行し、アプリ生成checkpointのPreProcessor入りメタデータを読み込んで契約照合を通過することを確認する。対応: `AC-003`、設計「受け入れ検証」。完了条件: 対象環境、メタデータと検査開始結果を証跡に記録する。
- [ ] 3.4 Ubuntu 24.04 LTSで学習から検査の全経路を実行し、報告された3件のエラーなく完了することを確認する。対応: `AC-004`、設計「受け入れ検証」。完了条件: 対象環境、使用した入力、全CLI結果を証跡に記録する。
- [x] 3.5 Ubuntu確認を延期する場合は `AC-001`〜`AC-004` と未完了タスク3.1〜3.4をREADMEへ引き継ぎ、受け入れ検証表を「未検証」のまま維持する。`npx --no-install openspec validate fix-anomalib-training-checkpoint --strict` と `--phase limited-archive` のトレーサビリティ検査を通す。対応: 全AC。完了条件: 引き継ぎ行と検査結果が一致する。
