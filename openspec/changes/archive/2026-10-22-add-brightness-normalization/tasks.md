## 1. 設定と準備指紋

- [x] 1.1 `src/app/common/config.py` の型番共通設定に `brightness_normalization` の既定値、厳密な型・範囲・有限性・大小関係の検証を追加する。対応: `REQ-027`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-001`、`TC-002`。完了条件: 省略値を読み込め、不正値を処理前に項目名付きで拒否できる。
- [x] 1.2 `src/app/common/config.py` の `preparation_fingerprint` に補正の有効・無効を含め、有効時は既定値展開後の全項目を学習・試験両方の指紋へ含める。対応: `REQ-025`、設計「データ契約と状態」「技術判断」、`TC-007`、`TC-008`、`TC-009`。完了条件: 条件変更が指紋へ反映され、無効時の無関係な項目変更は指紋を変えない。

## 2. 輝度計算と画像準備への接続

- [x] 2.1 `src/app/image_preparation/imaging.py` にBGR→グレースケールの範囲内統計、倍率制限、全チャンネルの四捨五入・飽和処理、値なし・対象値0以下の補正省略を追加する。対応: `REQ-028`、設計「技術判断」「境界条件と失敗モード」、`TC-003`、`TC-004`、`TC-005`。完了条件: 入力配列を変更せず、境界値と補正不能時の出力を再現できる。
- [x] 2.2 `src/app/image_preparation/preparation.py` の `prepare_training` と `prepare_testing` で、縮小済み基準画像の同じ範囲を切り出して補正を分割後・保存前に適用する。`enabled=false`、ブラックリスト、位置合わせ失敗の既存経路を維持する。対応: `REQ-028`、設計「処理フロー」「インターフェースと失敗時の結果」、`TC-003`、`TC-005`、`TC-006`。完了条件: 両準備の保存画像が同じ補正规則に従い、補正不能・無効時は元の分割画素を保存する。

## 3. 試験・文書・運用確認

- [x] 3.1 `tests/test_config.py` に `test_brightness_defaults` と `test_brightness_rejects_invalid_settings` を追加し、省略値、型、境界、大小関係、入力不備時の成果物保持を検証する。対応: `REQ-027` / `REQ-027-S01`・`REQ-027-S02`、設計「試験設計」、`TC-001`、`TC-002`。完了条件: `uv run --locked pytest tests/test_config.py -q` が成功する。
- [x] 3.2 `tests/test_preparation.py` に `test_brightness_normalizes_train_and_test_splits`、`test_brightness_gain_and_rounding_boundaries`、`test_brightness_skips_unavailable_statistics`、`test_brightness_disabled_preserves_splits` の pytest テストを追加し、実OpenCV・NumPyとPNG保存で画素値・元画像保持を検証する。対応: `REQ-028` / `REQ-028-S01`～`REQ-028-S04`、設計「試験設計」、`TC-003`、`TC-004`、`TC-005`、`TC-006`。完了条件: `uv run --locked pytest tests/test_preparation.py -q` が成功する。
- [x] 3.3 `tests/test_config.py` に `test_brightness_training_fingerprint`、`test_brightness_testing_fingerprint`、`test_brightness_changes_invalidate_preparation` の pytest テストを追加し、両manifest、全項目の指紋変化、旧準備成果物の拒否を検証する。対応: `REQ-025` / `REQ-025-S01`～`REQ-025-S03`、設計「試験設計」「移行とロールバック」、`TC-007`、`TC-008`、`TC-009`。完了条件: `uv run --locked pytest tests/test_config.py -q` が成功する。
- [x] 3.4 `README.md` の設定項目表に `brightness_normalization` の行を追加し、既定値、利用するCLI、設定変更後の `train-pre`・`train`・`test-pre`・`test` の再実行を案内する。`config/part_XX.json` は変更しない。対応: `REQ-027`、`REQ-028`、`REQ-025`、`AC-005`、設計「移行とロールバック」。完了条件: READMEの説明と設定モデル・再実行手順が一致する。
- [ ] 3.5 Ubuntu 24.04 LTSとWindows 11の対象実機で `AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005` を検証する。median・mean・無効化、値なし・ゼロ、不正設定、全項目の指紋変更を確認し、CPUと利用可能なGPUで全件・単独グループの準備・学習・検査と読戻しを行う。結果を `openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/acceptance.md` にコマンド・日付・環境・版・結果付きで記録し、designの「受け入れ検証」を更新する。対応: `AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005`、設計「受け入れ検証」。完了条件: 全AC-IDの検証範囲を対象環境の証跡で確認できる。実機を利用できず受け入れ確認だけを延期する場合は未完了のまま、READMEの「延期中の受け入れ確認」にAC-ID・本タスク番号・確認内容を記録する。
- [x] 3.6 `uv run --locked pytest`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change add-brightness-normalization --phase implementation` を実行し、全TC-IDの収集・成功と品質検査を確認する。verify / archive前は `npx --no-install openspec validate add-brightness-normalization --strict` と通常 `--phase complete`、実機確認だけを延期する場合は `--phase limited-archive` の対応検査を実行する。対応: `REQ-025`、`REQ-027`、`REQ-028`、`AC-001`～`AC-005`、設計「試験設計」「受け入れ検証」。完了条件: 自動試験・品質確認の結果を証跡に記録し、実機確認の状態と混同せずに判定する。
