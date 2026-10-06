# 受け入れ検証記録

- 実施日: 2026-10-07
- 環境: macOS 26.6.2 arm64、Python 3.13.15、OpenCV 5.0.0。
- 実行: `uv run --locked pytest tests/test_config.py tests/test_preparation.py -q` は43件成功。
- 実行: `uv run --locked pre-commit run --all-files` は全フック成功。
- 実行: `npm run check` は OpenSpec厳密検証、Ruff、Pyright、145件のpytest、リポジトリ検査、設計段階のトレーサビリティ検査に成功。
- 実行: `uv run --locked python scripts/check_openspec_traceability.py --change resize-and-knn-image-alignment --phase implementation` は参照テスト収集を含めて成功。
- 追加確認: `uv run --locked pytest tests/test_config.py tests/test_preparation.py tests/test_runtime.py -q` は49件成功。`test_resize_zero_dimension_is_processing_error` は有効倍率で1×1画像が0寸法となる場合の終了コード3、エラー理由、既存確認画像の維持を確認。

| 受け入れID | 確認内容 | 結果・範囲 |
| --- | --- | --- |
| AC-001 | 倍率0.5で基準画像・元画像が32×32から16×16になり、確認画像と学習・試験分割画像は縮小後の座標系で一辺8pxを保持する | `test_check_uses_resized_reference_and_original_crop_size`、`test_train_pre_resizes_before_alignment_and_keeps_crop_size`、`test_test_pre_resizes_before_alignment_and_keeps_crop_size` が成功。実画像ファイルとテスト用位置合わせ関数で確認 |
| AC-002 | KNN比率判定、境界の等号除外、候補不足、最低点数の成否、RANSAC条件、配布設定の項目存在と妥当性 | `test_align_orb_filters_knn_candidates`、`test_align_orb_uses_configured_ransac_contract`、`test_alignment_knn_settings_validation`、`test_distributed_image_and_alignment_settings_are_present` が成功。KNNマッチャーとホモグラフィはテストダブル、ORB特徴抽出は実OpenCV。指定既定値は `src/app/common/config.py` と `config/part_XX.json` をレビューし、運用で変わる配布設定値との一致を自動試験では固定しない |
| AC-003 | 不正倍率・KNN値、縮小後範囲外・0寸法、読込不能時の既存成果物維持、学習除外と試験未判定 | `test_resize_rejects_invalid_values`、`test_check_rejects_invalid_ranges`、`test_resize_zero_dimension_is_processing_error`、`test_alignment_knn_settings_validation`、`test_train_pre_warns_and_skips_alignment_failure`、`test_train_pre_rejects_out_of_bounds_crop_atomically`、`test_test_pre_rejects_out_of_bounds_crop`、`test_train_pre_read_failure_preserves_existing_output`、`test_test_pre_read_failure_preserves_existing_output`、既存の位置合わせ失敗試験が成功 |

AC-001〜AC-003のmacOS自動試験・設定レビューの範囲は上記のとおりである。<br />
Ubuntu 24.04 LTSとWindows 11の実機、運用画像による位置合わせ結果と画質、処理時間は未検証とし、設計の受け入れ検証とREADMEの延期記録にあるタスク4.1〜4.3へ引き継ぐ。<br />
この記録は対象OSでの受け入れ完了や運用開始の承認を意味しない。
