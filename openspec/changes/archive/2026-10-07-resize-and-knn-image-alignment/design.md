## 背景・前提

設定は `src/app/common/config.py`、画像処理は `src/app/image_preparation/imaging.py`、3つの準備経路は `preparation.py` にある。<br />
現行の基準画像、元画像、確認画像は原寸で扱われ、ORBは相互一致方式を使う。

## 目標・対象外

### 目標

- 基準画像と元画像を同倍率で位置合わせ前に縮小し、確認画像と分割座標を縮小後の座標系に統一する。
- ORB対応点を KNN 2候補の比率で選別し、指定値と既定値を検証する。

### 対象外

- 学習と評価の処理変更。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | 処理フロー、データ契約と状態 | 共通設定、確認画像 | 1.1, 1.2, 2.1 | TC-001, TC-002, TC-003, TC-014, TC-016 | 設定検証と確認画像試験 |
| REQ-002 | 処理フロー、技術判断 | ORB、学習準備 | 1.1, 1.2, 1.3, 2.2 | TC-004, TC-005, TC-006, TC-007, TC-008, TC-009, TC-015 | 対応点・分割・失敗試験 |
| REQ-003 | 処理フロー、インターフェースと失敗時の結果 | 試験準備 | 1.2, 1.3, 2.3 | TC-010, TC-011, TC-012, TC-013 | 分割・未判定試験 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 共通設定 | 変更 | INI、型番JSON | 検証済み倍率・位置合わせ条件 | 既存設定読込 | `common/config.py` に確定 |
| 確認・準備 | 変更 | 基準画像・元画像・倍率 | 縮小後確認画像・分割画像 | 画像処理 | `image_preparation/preparation.py` に確定 |
| 位置合わせ | 変更 | 縮小画像・設定 | 対応点数・整列画像 | OpenCV | `image_preparation/imaging.py` に確定 |

### 処理フロー

1. 設定読込時に倍率とKNN条件を検証する。旧INIで倍率未指定なら1とする。
2. `check` は基準画像を縮小してから既存の範囲描画と範囲検証を行う。
3. 学習・試験準備は基準画像を一度縮小し、各元画像も同倍率で縮小してから位置合わせする。
4. ORBは2候補を取得し、候補不足を除外して `best.distance < ratio_threshold * second.distance` の対応だけをホモグラフィへ渡す。失敗状態は従来のmanifestへ記録する。
5. 位置合わせ後は縮小後の座標を使い、従来の `IMAGE.SIZE` ピクセル四方を切り出す。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| `setting.ini` | 追加 | `IMAGE.RESIZE: float` (省略可) | 0 < 値 <= 1、既定1、配布設定0.5 | 運用者 | 旧設定は原寸を維持 |
| 型番JSONの `alignment` | 追加・変更 | `knn_k: int`、`ratio_threshold: float` (省略可) と既存条件 | 2、0 < 比率 < 1、既定0.75。最低点10、誤差8.0、信頼0.95、最低比率0.2 | 運用者 | 旧設定の明示値は維持 |
| 分割画像 | 内容変更 | サイズは `SIZE` 四方 | 縮小後座標 | 準備CLI | 既存派生成果物は再生成 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `check` | 運用者 → 確認処理 | 倍率、基準画像、範囲 | 縮小画像上の範囲 | 倍率不正・範囲外 → 入力エラー、縮小後0寸法 → 処理エラー。旧確認画像維持 | 設定または画像を修正して再実行 |
| `train-pre` | 運用者 → 学習準備 | 元画像、基準画像、条件 | 分割画像・manifest | 対応不足 → 学習除外、範囲外 → エラーと旧成果物維持 | 再実行で一式置換 |
| `test-pre` | 運用者 → 試験準備 | 元画像、基準画像、条件 | 分割画像・manifest | 対応不足 → 未判定、範囲外 → エラーと旧成果物維持 | 再実行で一式置換 |

## 技術判断

### 判断1: 縮小補間と適用位置

- **状態**: 確定。
- **採用内容**: OpenCV `INTER_AREA` で縮小し、基準画像と元画像の両方に適用する。倍率1は画素を変更しない。
- **根拠**: `INTER_AREA` は縮小時のエイリアシングを抑える。基準画像も縮小すると対応点と分割座標を同じ座標系で扱える。
- **代替案**: 元画像だけ縮小する案は基準画像との縮尺が異なる。後段のみ縮小する案は位置合わせ負荷を下げない。
- **実装規則 / 不変条件**: `SIZE` は倍率を掛けない。寸法は OpenCV の倍率指定に従い、0寸法となる入力は画像処理失敗として扱う。
- **影響**: 既存分割座標と派生成果物を見直す。

### 判断2: KNN比率判定

- **状態**: 確定。
- **採用内容**: Hamming距離で `knnMatch(..., k=2)` し、厳密な小なりで比率判定する。
- **根拠**: 利用者指定の `k=2` と `0.75` を設定として適用する。
- **代替案**: 相互一致方式は今回の指定を満たさない。
- **実装規則 / 不変条件**: 2候補未満は除外。選別後の数を最低点数・manifestへ渡す。RANSACと失敗分類は維持する。
- **影響**: 対応点数と位置合わせ成否が変化する。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 不正な倍率・KNN条件 | 設定読込 | 準備を開始しない | 項目名を示すエラー | CLI実行結果 | 設定修正後に再実行 |
| 特徴点・候補不足 | 位置合わせ | 学習除外または試験未判定 | `insufficient_matches` | manifest・警告 | 画像・条件を確認 |
| 縮小後の範囲外 | 確認・準備 | 旧成果物維持 | 範囲IDと画像寸法を示す | CLI実行結果 | 座標修正後に再実行 |
| 縮小後の画像寸法が0 | 画像処理 | 旧成果物維持 | 画像処理失敗、終了コード3 | CLI実行結果 | 画像寸法または倍率を見直して再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 倍率・KNN条件を読み込み時に検証 | 不正値試験 |
| 性能 | 位置合わせ前に画素数を縮小 | 寸法と処理時間を記録。時間の数値目標は未指定 |
| 運用 | 縮小後の確認画像で座標を見直す | `check` と準備画像を確認 |

## 移行とロールバック

1. `IMAGE.RESIZE = 0.5` に変更後、既存の分割座標を縮小後の確認画像で見直す。
2. 学習・試験の派生画像を再生成する。旧挙動へ戻す場合は倍率1に戻し、座標と派生成果物を再生成する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-001 | REQ-001-S01 | integration | 倍率0.5でcheck | 半寸法、同じSIZE | `tests/test_preparation.py::test_check_uses_resized_reference_and_original_crop_size` | はい | OpenCV、ローカル | 対象OS実機確認 (4.1) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-002 | REQ-001 | REQ-001-S02 | unit | 不正倍率 | 設定拒否 | `tests/test_config.py::test_resize_rejects_invalid_values` | はい | 設定、ローカル | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-003 | REQ-001 | REQ-001-S03 | unit | 不正base | 拒否 | `tests/test_config.py::test_base_rejects_paths_outside_model_root` | はい | 既存回帰 | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-004 | REQ-002 | REQ-002-S01 | integration | 倍率0.5で学習準備 | 半寸法で整列、SIZE四方 | `tests/test_preparation.py::test_train_pre_resizes_before_alignment_and_keeps_crop_size` | はい | 準備経路、ローカル | 対象OS実機確認 (4.1) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-005 | REQ-002 | REQ-002-S02 | integration | ブラックリスト | 除外 | `tests/test_preparation.py::test_train_pre_excludes_blacklist_entries` | はい | 既存回帰 | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-006 | REQ-002 | REQ-002-S03 | unit | 候補不足 | 対応不足を返す | `tests/test_preparation.py::test_align_orb_filters_knn_candidates` | はい | KNNテストダブル | 対象OS実機確認 (4.2) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-007 | REQ-002 | REQ-002-S04 | integration | 縮小後範囲外 | エラー、旧成果物維持 | `tests/test_preparation.py::test_train_pre_rejects_out_of_bounds_crop_atomically` | はい | 既存回帰 | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-008 | REQ-002 | REQ-002-S05 | integration | 読込不能 | 旧成果物維持 | `tests/test_preparation.py::test_train_pre_read_failure_preserves_existing_output` | はい | 入力失敗、ローカル | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-009 | REQ-002 | REQ-002-S06 | unit | 不正KNN条件 | 設定拒否 | `tests/test_config.py::test_alignment_knn_settings_validation` | はい | 設定、ローカル | 対象OS実機確認 (4.2) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-010 | REQ-003 | REQ-003-S01 | integration | 倍率0.5で試験準備 | 半寸法で整列、SIZE四方 | `tests/test_preparation.py::test_test_pre_resizes_before_alignment_and_keeps_crop_size` | はい | 準備経路、ローカル | 対象OS実機確認 (4.1) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-011 | REQ-003 | REQ-003-S02 | integration | 位置合わせ失敗 | 未判定 | `tests/test_preparation.py::test_test_pre_carries_alignment_failure` | はい | 既存回帰 | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-012 | REQ-003 | REQ-003-S03 | integration | 範囲外 | エラー | `tests/test_preparation.py::test_test_pre_rejects_out_of_bounds_crop` | はい | 既存回帰 | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-013 | REQ-003 | REQ-003-S04 | integration | 読込不能 | 旧成果物維持 | `tests/test_preparation.py::test_test_pre_read_failure_preserves_existing_output` | はい | 入力失敗、ローカル | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-014 | REQ-001 | REQ-001-S02 | integration | 不正SIZE・重複ID・範囲外 | 拒否、旧確認画像維持 | `tests/test_config.py::test_check_rejects_invalid_ranges` | はい | 設定・確認画像、ローカル | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-015 | REQ-002 | REQ-002-S03 | integration | 位置合わせ失敗 | 全分割を学習から除外 | `tests/test_preparation.py::test_train_pre_warns_and_skips_alignment_failure` | はい | 準備経路、ローカル | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| TC-016 | REQ-001 | REQ-001-S02 | integration | 縮小後0寸法 | 終了コード3、旧確認画像維持 | `tests/test_runtime.py::test_resize_zero_dimension_is_processing_error` | はい | CLI・画像処理、ローカル | 対象OS実機確認 (4.3) | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-001 | 3 | 5 | なし | 網羅 |
| REQ-002 | 6 | 7 | なし | 網羅 |
| REQ-003 | 4 | 4 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | macOS 26.6.2 arm64・OpenCV 5.0.0の自動試験は成功。Ubuntu 24.04 LTS・Windows 11実機で倍率0.5の確認・学習・試験を確認する | TC-001、TC-004、TC-010とタスク4.1の実機確認 | 両OS実機で縮小後の確認画像・分割画像の寸法と切り出しSIZEを確認する (4.1) | 未検証 | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| AC-002 | macOSの自動試験と設定レビューは成功。両OS実機で運用画像を使いKNN比率判定と位置合わせ結果を確認する | TC-006、TC-009、既存RANSAC試験とタスク4.2の実機確認 | 両OS実機で対応点数・成功または失敗理由・処理時間と画像の画質を確認する (4.2) | 未検証 | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
| AC-003 | macOSの自動試験は成功。両OS実機で不正設定・範囲外・位置合わせ失敗時の扱いを確認する | TC-002、TC-007〜TC-013、TC-014、TC-015、TC-016とタスク4.3の実機確認 | 両OS実機で終了コード、既存成果物維持、学習除外と試験未判定を確認する (4.3) | 未検証 | openspec/changes/archive/2026-10-07-resize-and-knn-image-alignment/evidence/acceptance.md |
