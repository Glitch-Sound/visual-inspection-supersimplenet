# 最新仕様と実装・試験の照合

2026-10-09に `openspec/specs/` の3仕様、24要件、68 Scenarioを対象に、`src/app/` と `tests/` を双方向に確認した。<br />
以下のS番号は同じ行の要件IDに属する。試験欄は直接確認する主なテストであり、`npm run check` は全テストを実行する。

| 要件とScenario | 実装の主な位置 | 試験の主な位置 | 判定 |
| --- | --- | --- | --- |
| REQ-001 S01/S02/S03/S04 | `common/config.py`、`common/paths.py`、`image_preparation/imaging.py`、`image_preparation/preparation.py` | `test_config.py`、`test_preparation.py::test_change_req_001_01`〜`04` | 対応 |
| REQ-002 S01/S02/S03/S04/S05/S06 | `image_preparation/preparation.py`、`image_preparation/imaging.py`、`common/atomic.py` | `test_preparation.py::test_change_req_002_01`〜`06` | 対応 |
| REQ-003 S01/S02/S03/S04 | `image_preparation/preparation.py`、`image_preparation/imaging.py`、`common/atomic.py` | `test_preparation.py::test_change_req_003_01`〜`04` | 対応 |
| REQ-017 S01/S02 | `image_preparation/cli.py`、`common/cli.py` | `test_preparation.py::test_change_req_017_01`〜`02`、`test_runtime.py` | 対応 |
| REQ-004 S01/S02/S03 | `model_training/search.py`、`model_training/cli.py`、`common/contracts.py`、`common/paths.py` | `test_training.py::test_split_groups_by_source_image`、`test_split_rejects_insufficient_source_images`、`test_train_rejects_invalid_prepared_manifest`、`test_train_rejects_symlinked_prepared_input`、`test_train_cli_accepts_valid_prepared_images` | 対応 |
| REQ-005 S01/S02 | `model_training/search.py`、`model_training/trainer.py`、`model_training/cli.py` | `test_training.py::test_search_selects_lowest_validation_percentile`、`test_search_report_labels_objective_as_provisional` | 対応 |
| REQ-006 S01/S02 | `model_training/augmentation.py`、`model_training/trainer.py`、`common/config.py` | `test_training.py::test_augmentation_defaults_order_and_seed`、`test_augmentation_is_training_only_and_ephemeral`、`test_validation_pipeline_disables_augmentation` | 対応。個々の乱数分布の統計的検証は未実施 |
| REQ-007 S01/S02/S03/S04 | `model_training/artifacts.py`、`model_training/trainer.py`、`common/artifact_transaction.py`、`common/model_adapter.py`、`model_evaluation/evaluation.py` | `test_training.py::test_training_persists_best_model_and_threshold`、`test_pretrained_weights_are_cached`、`test_training_artifact_transaction_restores_previous_set`、`test_evaluation.py::test_evaluation_rejects_invalid_best_trial_contract` | S02の実際のモデル生成経路によるキャッシュ再利用は未検証 |
| REQ-008 S01/S02 | `model_training/search.py`、`model_training/artifacts.py`、`model_training/cli.py` | `test_training.py::test_training_resumes_existing_study`、`test_training_restart_replaces_only_derived_artifacts` | 対応 |
| REQ-014 S01 | `model_training/trainer.py` | `test_training.py::test_trial_runner_uses_all_validation_images`、`test_anomalib_uses_complete_validation_folder` | 対応 |
| REQ-015 S01 | `common/model_adapter.py`、`model_training/trainer.py` | `test_training.py::test_tunable_model_is_pickleable_and_uses_trial_multiplier`、`test_tunable_model_saves_lightning_checkpoint` | 対応 |
| NREQ-004 S01/S02/S03 | `model_training/cli.py`、`model_training/search.py` | `test_training.py::test_search_reports_trial_conditions`、`test_search_reports_trial_outcomes`、`test_search_reports_resumed_trial_count` | 対応 |
| REQ-020 S01/S02 | `common/model_adapter.py`、`model_training/artifacts.py`、`model_training/cli.py` | `test_training.py::test_model_adapter_uses_tv_backbone`、`test_training_restart_replaces_only_derived_artifacts` | 実重みを使う対象OSの学習・検査は未検証 |
| REQ-009 S01/S02 | `common/runtime.py`、`common/cli.py` | `test_runtime.py::test_select_device_prefers_available_cuda`、`test_select_device_falls_back_to_cpu` | 対応。対象OSの実GPUは未検証 |
| REQ-010 S01/S02/S03/S04 | `model_evaluation/predictor.py`、`model_evaluation/evaluation.py` | `test_evaluation.py::test_evaluation_records_normal_split`、`test_evaluation_visualizes_anomalous_split`、`test_predictor_uses_model_preprocessor`、`test_heatmap_uses_shared_range_across_images` | 対応 |
| REQ-011 S01/S02/S03 | `model_evaluation/results.py`、`model_evaluation/evaluation.py` | `test_results.py::test_aggregate_prefers_anomaly`、`test_aggregate_accepts_only_all_normal`、`test_aggregate_marks_incomplete_result_undetermined` | 対応 |
| REQ-012 S01/S02/S03/S04 | `common/contracts.py`、`model_evaluation/evaluation.py`、`model_evaluation/cli.py` | `test_results.py::test_result_json_contains_traceable_contract`、`test_result_contract_rejects_invalid_score_and_runtime`、`test_evaluation.py::test_evaluation_keeps_same_stem_different_extensions`、`test_evaluation_rejects_invalid_manifest_before_prediction`、`test_evaluation_rejects_symlinked_prepared_input`、`test_test_cli_restart_preserves_results_for_invalid_manifest` | 対応 |
| REQ-013 S01 | `model_evaluation/evaluation.py`、`model_evaluation/cli.py` | `test_evaluation.py::test_evaluation_restart_replaces_only_results` | 対応 |
| NREQ-001 S01/S02 | `common/runtime.py`、各CLI、`scripts/run_visual_inspection_smoke.py` | `test_platform_smoke.py::test_workflow_records_runtime_contract`、`test_workflow_completes_with_cpu_fallback` | Ubuntu 24.04 LTS・Windows 11の実機確認は未検証。READMEの延期記録を参照 |
| REQ-016 S01/S02 | `model_evaluation/predictor.py`、`model_evaluation/cli.py`、`model_evaluation/evaluation.py` | `test_evaluation.py::test_test_cli_validates_checkpoint_before_model_construction`、`test_test_cli_rejects_checkpoint_contract_before_model_construction` | 対応 |
| REQ-018 S01/S02/S03/S04/S05/S06 | `common/config.py`、`model_evaluation/evaluation.py` | `test_evaluation.py::test_change_req_018_01`〜`06` | 対応 |
| REQ-019 S01/S02 | `common/config.py`、`common/contracts.py`、`model_evaluation/evaluation.py` | `test_evaluation.py::test_heatmap_uses_shared_range_across_images`、`test_evaluation_rejects_invalid_heatmap_range_before_prediction` | 対応 |
| NREQ-002 S01/S02 | `common/cli.py`、各能力のCLI | `test_runtime.py::test_change_nreq_002_01`〜`02` | 対応 |
| NREQ-003 S01/S02/S03/S04 | `model_evaluation/cli.py`、`model_evaluation/evaluation.py` | `test_runtime.py::test_evaluation_progress_uses_bar_on_terminal`、`test_test_cli_reports_source_progress_non_tty`、`test_evaluation.py::test_evaluation_progress_counts_undetermined_and_split_errors`、`test_evaluation_progress_stops_on_fatal_failure` | 対応 |

## 逆方向の確認

`src/app/image_preparation/` の公開処理は REQ-001〜003、REQ-017 に対応する。<br />
`src/app/model_training/` の公開処理は REQ-004〜008、REQ-014、REQ-015、REQ-020、NREQ-004 に対応する。<br />
`src/app/model_evaluation/` の公開処理は REQ-009〜013、REQ-016、REQ-018、REQ-019、NREQ-001〜003 に対応する。<br />
`src/app/common/` は上記能力の設定、契約、パス、実行記録を共有する。<br />
`model_training/trainer.py::ensure_cached` とその単体テストは残っているが、実際のモデル生成からは呼ばれていない。実モデルの重み取得は `timm` のキャッシュ機構に委ねられており、S02のアプリ経路での再取得有無はこの単体テストだけでは証明できない。

## 未確認の範囲

- 対象OSと実GPU、実事前学習重みを使う総合実行は、このmacOS環境では実施できない。READMEの「延期中の受け入れ確認」に既存の追跡記録がある。
- REQ-007-S02の実モデル生成経路で、キャッシュ存在時に再ダウンロードしないことは自動試験で直接確認していない。
- REQ-006の確率・一様分布はコードと設定値を照合し、seed再現・適用順序を自動試験した。分布の統計的な試験はない。
