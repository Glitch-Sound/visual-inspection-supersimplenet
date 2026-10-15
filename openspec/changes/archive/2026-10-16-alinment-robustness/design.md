## 背景・前提

現行の型番共通設定は `src/app/common/config.py` の `AlignmentSettings` が読み、`src/app/image_preparation/imaging.py` の `align_orb` がORB対応点、RANSACによるホモグラフィ推定、黒埋めの画像変換を行う。<br />
`preparation.py` は学習・試験の元画像を一度ずつ位置合わせして分割し、`common/contracts.py` の `AlignmentResult` を準備manifestへ保存する。<br />
`preparation_fingerprint` は位置合わせ設定の `model_dump()` を含める。<br />
`train` と `test` は保存した指紋と現在の設定を照合する。<br />
学習入力の平行移動 `max_ratio` は分割画像の幅・高さに対する比率、回転 `max_degrees` は角度であり、既存の `model_training/augmentation.py` が学習時だけ適用する。

## 目標・対象外

### 目標

- 既定の分割画像の画素を維持しつつ、`homography` / `similarity` と `black` / `replicate` の組み合わせを選択できる。
- 成功した元画像ごとの縮小後ピクセル単位のインライア再投影RMSEを学習・試験manifestに保存する。
- 運用者が誤差分布と実画像から既存の平行移動・回転強度を調整し、準備から検査まで再実行できる。

### 対象外

- 誤差からの拡張強度の自動決定。RMSEだけでは残り変位の方向と回転成分を区別できない。
- 検査の判定規則、閾値、モデル構造の変更。
- 位置ズレによる誤検出のゼロ保証。本番性能の受け入れ基準は別途決める。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-002 | 業務フローと責務、技術判断、境界条件と失敗モード | 型番設定→学習画像準備 | 1.1、1.2、2.1 | TC-001〜TC-013 | 設定検証、画素、除外、成果物保持のunit / integration |
| REQ-003 | 業務フローと責務、インターフェースと失敗時の結果 | 型番設定→試験画像準備 | 1.2、2.2 | TC-014〜TC-019 | 画素、未判定、成果物保持のintegration |
| REQ-025 | データ契約と状態、移行とロールバック | 設定→準備指紋→学習・検査 | 1.1、2.3 | TC-020〜TC-022 | 指紋の差分、旧準備結果の拒否 |
| REQ-039 | データ契約と状態、技術判断 | 位置合わせ→準備manifest→運用者 | 1.2、1.3、2.4 | TC-023〜TC-025 | 計算値、manifest、失敗時の欠落 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 型番共通設定と準備指紋 | 変更 | `alignment` の二つの選択値 | 検証済み設定と新指紋 | 学習・試験準備、学習・検査 | `common/config.py` に確定。既存の所有責務を維持 |
| ORB位置合わせ | 変更 | 縮小後元画像・基準画像・設定 | 位置合わせ画像、マッチ数、インライア比率、RMSEまたは失敗理由 | 設定、画像処理ライブラリ | `image_preparation/imaging.py` に確定。能力境界内の責務 |
| 準備manifest | 変更 | 位置合わせ結果 | 元画像別の誤差、状態、分割参照 | 共通の保存契約 | `common/contracts.py` と `image_preparation/preparation.py` に確定 |
| 誤差確認と強度調整 | 追加 | 学習・試験manifest、分割画像 | 運用者による拡張強度の設定と再実行 | README、既存の学習設定 | READMEに確定。自動調整処理は追加しない |

### 処理フロー

1. 運用者が型番設定の変換モデルと境界埋めを選び、`train-pre` または `test-pre` を起動する。<br />
   設定読込み時に選択値を検証し、不正なら準備成果物へ触れずに終了する。
2. 画像準備は基準画像と元画像を既存の倍率で縮小し、既存のORB対応点フィルタを適用する。<br />
   `homography` は従来の射影変換、`similarity` は平行移動・回転・等方拡大縮小に限る変換をRANSACで推定する。
3. 推定結果・マスク・インライア比率・RMSEを確認する。<br />
   推定不能、インライアなし、非有限または特異な変換、非有限RMSEは位置合わせ失敗にする。<br />
   学習なら全分割を除外し、試験なら未判定と再撮影要否を記録する。
4. 成功画像を選択した境界埋めで変換して分割し、元画像ごとのRMSEをmanifestへ保存する。<br />
   全グループ学習準備では一回の位置合わせ結果を共有する。
5. 運用者はREADMEの手順で学習・試験の誤差分布と分割画像を確認して拡張強度を設定し、`train-pre`、`train`、`test-pre`、`test` を再実行する。<br />
   学習・検査開始時の指紋不一致は既存の拒否経路で処理する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番共通 `alignment` | 追加 | `transform_model: Literal["homography", "similarity"]`、`border_mode: Literal["black", "replicate"]` (省略可) | 既定は `homography` と `black`。未知値は拒否 | 運用者が設定、共通設定契約が検証 | 旧設定を読める。追加値は指紋に含める |
| 位置合わせ結果 | 追加 | `inlier_reprojection_rmse_px: float` (成功時) | 有限、0以上、縮小後ピクセル単位 | 画像準備の位置合わせ | 学習・試験へ同じ値を渡す |
| manifestの `sources[].alignment` | 追加 | `inlier_reprojection_rmse_px: float \| null` (旧manifestと失敗時はnull) | 新規の成功結果では必須、失敗時はnull | 学習・試験準備 | 旧manifestは読戻し可能。旧指紋で学習・検査へ流用しない |
| 準備指紋 | 変更 | SHA-256文字列 | 選択値を既定値も含めて計算。グループ別の学習条件は従来どおり除外 | 共通設定契約 | 新版導入時に旧指紋と不一致。対象型番の再準備が必要 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train-pre` | 運用者→画像準備 | 型番、任意のグループ | 分割画像と元画像別誤差を持つmanifest | 設定不備は終了コード2、位置合わせ失敗画像は除外・警告、読込みや保存の失敗は終了コード3で既存成果物を維持 | 修正・再実行で対象の準備一式を置換。タイムアウト新設なし |
| `test-pre` | 運用者→画像準備 | 型番 | 分割画像と元画像別誤差を持つmanifest | 設定不備は終了コード2、位置合わせ失敗画像は未判定・再撮影要否、読込みや保存の失敗は終了コード3で既存成果物を維持 | 再実行で準備一式を置換。タイムアウト新設なし |
| `train` / `test` | 運用者→学習・検査 | 現在設定と準備manifest | 指紋一致時に既存処理 | 不一致は理由を示して開始を拒否。再準備が必要 | 準備後に再実行 |

## 技術判断

### 判断: 制限付き変換の推定と既定動作

- **状態**: 確定。
- **採用内容**: `homography` は既存の `findHomography` と `warpPerspective` の呼出しを維持する。`similarity` は `estimateAffinePartial2D` のRANSAC結果を使い `warpAffine` で変換する。両方とも同じORB対応点フィルタ、RANSAC閾値・信頼確率、最低インライア比率を用いる。
- **根拠**: 制限付き変換はせん断・非等方拡大縮小・射影を含まない。既定の経路を維持すれば既存設定で画素一致を検証できる。
- **代替案**: `estimateAffine2D` はせん断と非等方拡大縮小を許すため採用しない。全画像をホモグラフィに通してから行列を制限する方式はRANSACのインライア判定と整合しない。
- **実装規則 / 不変条件**: 画像寸法は基準画像に合わせる。`black` は既存の既定の黒埋め、`replicate` は端画素複製とする。成功の前に空マスク、0インライア、非有限・特異な行列、非有限RMSEを検知する。
- **影響**: 設定検証と位置合わせ処理に限定。制限付き変換の採用で位置合わせ成否と分割画素は変わり得る。

### 判断: 残り誤差の定義と互換性

- **状態**: 確定。
- **採用内容**: RANSACマスク内の元画像対応点を選択した変換で基準画像座標へ投影し、対応点との二次元距離の二乗平均平方根を算出する。点座標は縮小後のものを使う。元画像単位で値を保持し、学習ではグループmanifestへ同じ値を複写する。
- **根拠**: 個別値を残せば学習・試験の分布を後から計算できる。RMSEは大きい残りずれを見落としにくい。
- **代替案**: 分布要約だけを保存すると原因画像を確認できない。全対応点を含めると外れ値で残り誤差を過大評価するため採用しない。
- **実装規則 / 不変条件**: 新たに生成した成功結果では値を必ず保存する。旧manifestの読戻しと失敗画像にはnullを許容する。失敗画像に0を代入しない。
- **影響**: 共有契約、準備manifest、READMEの確認手順に追加。既存の判定スコアには影響しない。

### 判断: データ拡張の調整

- **状態**: 確定。
- **採用内容**: READMEに成功画像のRMSEを学習・試験別に集計する手順、分割画像の縁とずれの確認、`translation.max_ratio` と `rotation.max_degrees` を調整する手順を記載する。RMSEは平行移動のピクセル目安として分割サイズで割って比較する。回転はRMSEだけで算出せず、実画像で見える回転と正常画像のばらつきから決める。
- **根拠**: 既存の学習拡張は設定可能であり、新規の自動調整処理を要しない。RMSEは回転・平行移動などを混ぜた一つの量である。
- **代替案**: RMSEをそのまま回転角へ変換することは、回転中心からの距離が不明で誤解を招くため採用しない。
- **実装規則 / 不変条件**: 設定した強度が欠陥を隠したり新たな偽像を作らないか、実画像と検査結果で確認する。試験・検証入力へ拡張を適用しない。
- **影響**: READMEと運用手順。学習時のデータ拡張実装は変更しない。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 未知の変換・境界埋め | 共通設定契約 | 準備開始前に拒否し既存成果物保持 | 項目名と入力不備 | 既存CLI stderr | 設定を修正して再実行 |
| 対応点不足、推定不能、空マスク、0インライア、無効な変換・RMSE | 画像準備 | 学習は画像全体を除外、試験は未判定。RMSEはnull | 元画像名と理由、試験は再撮影要否 | manifestと既存CLI警告 | 元画像や設定を確認して再準備 |
| 分割範囲外、読込み・保存失敗 | 画像準備 | 準備一式の更新を中断し旧成果物保持 | 失敗箇所を示して処理失敗 | 既存CLI stderr | 入力を修正して再実行 |
| 準備指紋不一致 | 学習・検査の読戻し境界 | 学習・検査開始を拒否 | `train-pre` または `test-pre` の再実行を案内 | 既存CLI stderr | 型番の準備をやり直す |
| 元画像の縁自体が黒い | 運用者の確認 | 端画素複製でも黒画素になり得る | 黒埋め由来の帯と区別して確認 | 実画像の受け入れ記録 | 撮影・分割範囲・設定を再評価 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 選択値を列挙型として検証し、誤差は有限・0以上だけ保存する | 不正値で既存成果物が変わらないことを自動試験で確認 |
| 性能 | `similarity` の推定とRMSE集計は元画像ごとに一度行う | 対象OSの実画像で準備時間を記録。新しい上限目標は未設定 |
| 運用 | READMEで誤差分布、縁、学習強度、再実行を一続きの手順として説明する | 対象OSと運用画像の受け入れ記録で確認 |
| 認証・外部連携 | 既存のローカルCLI範囲内で追加なし | 該当する権限・通知境界なし |

## 移行とロールバック

1. 旧設定はそのまま読めるが、指紋に新しい既定値が含まれるため旧準備結果は学習・検査に流用できない。<br />
   対象型番の設定と元画像を確認し、`train-pre`、`train --restart`、`test-pre`、`test` を実行する。`train --restart` は新しい分割画像と拡張強度で探索・学習済みモデルを作り直すために使う。
2. 採用設定を戻す場合は変換を `homography`、埋め方を `black` に戻し、同じ順序で準備からやり直す。<br />
   旧モデル・旧結果の恒久保管は既存の対象外であり、必要な退避は運用者が切替前に行う。
3. 成功条件は新指紋で学習・試験準備が読め、学習済みモデルと結果が現行参照で読めること。<br />
   実画像で位置ズレ起因の誤検出を評価するまで本番利用の承認とはしない。

## 試験設計

各TCのpytest参照は実装先を示す。既存Scenarioの試験は該当テストを再実行し、追加条件がある場合は同じファイル内で拡張する。<br />
「残る検証」の実機確認は対象OSの実画像で行う。設計時点の証跡は未作成である。

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-002 | REQ-002-S01 | integration | 有効画像で全件`train-pre` | 分割画像、元画像不変 | `tests/test_preparation.py::test_group_req_002_s01` | はい | 固定画像の準備 | 実機画像、4.1〜4.6 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-002 | REQ-002 | REQ-002-S02 | integration | ブラックリストで準備 | 対象分割除外 | `tests/test_preparation.py::test_group_req_002_s02` | はい | 除外記録 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-003 | REQ-002 | REQ-002-S03 | integration | 対応点不足で準備 | 全分割除外、理由 | `tests/test_preparation.py::test_group_req_002_s03` | はい | 失敗伝播 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-004 | REQ-002 | REQ-002-S04 | integration | 範囲外で準備 | エラーと未完成成果物なし | `tests/test_preparation.py::test_group_req_002_s04` | はい | 範囲境界 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-005 | REQ-002 | REQ-002-S05 | integration | 読込不能画像で準備 | 旧成果物保持 | `tests/test_preparation.py::test_group_req_002_s05` | はい | 原子的な保存 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-006 | REQ-002 | REQ-002-S06 | unit | 不正KNN設定で読込 | 設定拒否 | `tests/test_preparation.py::test_group_req_002_s06` | はい | 設定境界 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-007 | REQ-002 | REQ-002-S07 | integration | 単独グループ準備 | 他グループ保持 | `tests/test_preparation.py::test_group_req_002_s07` | はい | グループ境界 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-008 | REQ-002 | REQ-002-S08 | integration | 共通分割の全件準備 | 一致する画像・位置合わせ | `tests/test_preparation.py::test_group_req_002_s08` | はい | 共有結果 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-009 | REQ-002 | REQ-002-S09 | unit | 選択値なしで準備 | 旧経路と画素一致 | `tests/test_imaging_core.py::test_alignment_default_pixels_match_legacy` | はい | 実OpenCV、固定画像 | 実機画像、4.1〜4.6 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-010 | REQ-002 | REQ-002-S10 | unit | 非黒端画素を外側へ変換 | 複製色、黒帯なし | `tests/test_imaging_core.py::test_alignment_replicate_border_pixels` | はい | 実OpenCV、画素 | 実機画像、4.1〜4.6 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-011 | REQ-002 | REQ-002-S11 | unit | similarity設定で位置合わせ | 平行移動・回転・等方拡大縮小のみ | `tests/test_imaging_core.py::test_alignment_similarity_transform` | はい | 実OpenCV、行列形状と画素 | 実機画像、4.1〜4.6 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-012 | REQ-002 | REQ-002-S12 | integration | 不正選択値と旧成果物 | 入力不備、旧成果物保持 | `tests/test_config.py::test_alignment_choices_rejected` | はい | 設定読込と準備境界 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-013 | REQ-002 | REQ-002-S13 | integration | 推定不能・0インライアで準備 | 除外、理由 | `tests/test_preparation.py::test_alignment_estimation_failure_excludes_training` | はい | 失敗伝播 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-014 | REQ-003 | REQ-003-S01 | integration | 試験準備 | 全分割保存、ブラックリスト非適用 | `tests/test_preparation.py::test_req_003_s01` | はい | 試験準備 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-015 | REQ-003 | REQ-003-S02 | integration | 失敗画像で試験準備 | 未判定、再撮影要否 | `tests/test_preparation.py::test_req_003_s02` | はい | 失敗伝播 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-016 | REQ-003 | REQ-003-S03 | integration | 範囲外で試験準備 | エラー | `tests/test_preparation.py::test_req_003_s03` | はい | 範囲境界 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-017 | REQ-003 | REQ-003-S04 | integration | 読込不能で試験準備 | 旧成果物保持 | `tests/test_preparation.py::test_req_003_s04` | はい | 原子的な保存 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-018 | REQ-003 | REQ-003-S05 | integration | similarityとreplicateで試験準備 | 黒帯由来画素なし | `tests/test_preparation.py::test_similarity_replicate_testing_pixels` | はい | 実OpenCVと保存画像 | 実機画像、4.1〜4.6 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-019 | REQ-003 | REQ-003-S06 | integration | 推定失敗で試験準備 | 未判定、分割なし | `tests/test_preparation.py::test_alignment_estimation_failure_undetermines_testing` | はい | 失敗伝播 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-020 | REQ-025 | REQ-025-S01 | integration | グループ別学習準備 | 指紋を保存 | `tests/test_preparation.py::test_group_req_025_s01` | はい | manifest指紋 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-021 | REQ-025 | REQ-025-S02 | integration | 試験準備、学習条件変更 | 指紋不変 | `tests/test_preparation.py::test_group_req_025_s02` | はい | 指紋の対象範囲 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-022 | REQ-025 | REQ-025-S03 | integration | 準備後に位置合わせ選択値変更 | 学習・検査を拒否 | `tests/test_preparation.py::test_alignment_options_change_fingerprint` | はい | 指紋と読戻し | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-023 | REQ-039 | REQ-039-S01 | integration | 異なる誤差の学習画像と共有グループ | 元画像別RMSE、共有値一致 | `tests/test_preparation.py::test_training_alignment_rmse_manifest` | はい | 計算値とmanifest | 実機分布、4.1〜4.6 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-024 | REQ-039 | REQ-039-S02 | integration | 複数の試験画像で準備 | 元画像別RMSE、分布抽出可 | `tests/test_preparation.py::test_testing_alignment_rmse_manifest` | はい | 計算値とmanifest | 実機分布、4.1〜4.6 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| TC-025 | REQ-039 | REQ-039-S03 | integration | 位置合わせ失敗で両準備 | 誤差null、除外・未判定 | `tests/test_preparation.py::test_failed_alignment_rmse_is_null` | はい | manifestと失敗状態 | なし | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-002 | 13 | 13 | なし | 網羅 |
| REQ-003 | 6 | 6 | なし | 網羅 |
| REQ-025 | 3 | 3 | なし | 網羅 |
| REQ-039 | 3 | 3 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 既定設定で旧版と同じ分割画素 | TC-009と固定画像の比較 | 実画像の確認 (4.1) | 未検証 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| AC-002 | 非黒端画素を持つ位置ズレ画像の黒帯 | TC-010、TC-018、実画像の目視比較 | 対象OS実画像の確認 (4.2) | 未検証 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| AC-003 | 両変換の成否、不正設定、旧成果物 | TC-011〜TC-013、TC-019 | 対象OS実画像の確認 (4.3) | 未検証 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| AC-004 | 学習・試験manifestの成功・失敗画像のRMSE | TC-023〜TC-025、分布集計 | 対象OS実画像の分布確認 (4.4) | 未検証 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| AC-005 | READMEの調整・再実行手順と指紋不一致 | 手順レビュー、TC-022、対象型番で一連の実行 | 対象OSの一連の実行 (4.5) | 未検証 | openspec/changes/archive/2026-10-16-alinment-robustness/evidence/implementation.md |
| AC-006 | Ubuntu 24.04 LTS / Windows 11の実画像で検査結果を比較 | 現行・新設定の分割画像、誤差分布、検査結果、所要時間を記録し運用者が判断 | 対象OS実機の確認 (4.6) | 未検証 | 未作成 |

## 未決事項

| 質問 | 回答期限 / 必要な工程 | 決定者 | 影響・未回答時の扱い |
| --- | --- | --- | --- |
| 実画像で採用する変換・境界埋め・拡張強度、誤検出を許容する基準 | 運用開始前 | 型番設定・学習の運用者と検査結果の評価者 | 実装と自動試験は進められるが、本番採用と性能達成は判定しない |
