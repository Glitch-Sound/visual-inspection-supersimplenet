## 背景・前提

現行の `ModelConfig` は型番共通条件を `src/app/common/config.py` で検証し、`preparation_fingerprint` が準備に影響する条件をハッシュ化する。<br />
`prepare_training` と `prepare_testing` は基準画像を縮小し、元画像を縮小・位置合わせして分割し、段階領域で画像とmanifestを完成させてから公開する。<br />
画像処理は `src/app/image_preparation/imaging.py`、準備の接続は `src/app/image_preparation/preparation.py` にある。<br />
正式仕様 `visual-inspection/image-preparation` の既存の失敗・再実行契約と、`openspec/structure.md` の能力境界を維持する。<br />
新しい外部連携はない。

## 目標・対象外

### 目標

- 型番共通の補正条件を厳密に検証し、省略時も既定値で動作させる。
- 縮小済み基準画像の同じ分割位置を目標として、学習・試験の分割画像に同一の補正を適用する。
- 補正不能・無効化時は分割画像の画素を変えず、条件変更は準備指紋で検出する。

### 対象外

- `check`、元画像、基準画像、学習・検査の推論処理の補正。
- 旧成果物との互換処理、自動移行、`config/part_XX.json` の更新。
- 本番検出性能の新しい合格数値。入力補正だけを変更するため。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-027 | データ契約と状態、インターフェースと失敗時の結果 | 型番設定の読込み・拒否 | 1.1、3.1 | TC-001、TC-002 | 設定読込みとCLIの入力不備をpytestで確認 |
| REQ-028 | 処理フロー、技術判断、境界条件と失敗モード | 輝度計算・補正、両準備への接続 | 2.1、2.2、3.2 | TC-003、TC-004、TC-005、TC-006 | 画素単位と学習・試験の保存画像をpytestで確認 |
| REQ-025 | データ契約と状態、移行とロールバック | 準備指紋、manifestと後続の整合検査 | 1.2、3.3 | TC-007、TC-008、TC-009 | 指紋差分と旧成果物拒否をpytestで確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 型番共通条件の検証 | 追加 | JSONの `brightness_normalization` | 検証済み設定または入力不備 | CLIの既存設定読込み | `src/app/common/config.py` に確定。既存の `ModelConfig` が型番共通条件を持つため |
| 輝度値と補正画素の計算 | 追加 | BGR分割画像2枚と検証済み条件 | 新しい分割画像または補正前画像 | 既存の画像配列契約 | `src/app/image_preparation/imaging.py` に確定。画像計算の責務があるため |
| 学習・試験分割への適用 | 変更 | 縮小済み基準画像、位置合わせ済み画像、範囲 | 補正済み分割画像と既存形式のmanifest | 画像計算 | `src/app/image_preparation/preparation.py` に確定。分割と公開の順序を管理するため |
| 準備条件の照合 | 変更 | 検証済み型番設定 | 学習・試験の準備指紋 | manifestと後続の既存照合 | `src/app/common/config.py` に確定。指紋生成が既にあるため |

### 処理フロー

1. 運用者が型番のCLIを起動すると、共通設定境界が補正設定を検証する。<br />
   型・範囲・大小関係の不備は既存の入力不備経路で終了し、準備成果物に触れない。
2. `train-pre` または `test-pre` は基準画像を一度縮小し、元画像を縮小・位置合わせする。<br />
   位置合わせ失敗時の除外・未判定は既存契約どおりとする。
3. 分割ごとに位置合わせ済み画像と縮小済み基準画像を、同じ換算座標・`SIZE` で切り出す。<br />
   `enabled=true` なら補正を計算し、`false` なら元の分割画像を使う。<br />
   値なし・対象輝度0以下も元の分割画像を使う。
4. 既存の段階領域に画像とmanifestを保存し、準備指紋を付けて公開する。<br />
   後続の学習・検査は既存の指紋照合で条件変更を検知する。
5. 条件変更後、運用者が `train-pre`、`train`、`test-pre`、`test` を再実行する。<br />
   分割位置確認が必要なら `check` も先に実行する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番設定 | 追加 | `brightness_normalization`: オブジェクト、省略可 | 省略時は全項目の既定値 | 運用者、設定読込み | サンプル設定は変更しない |
| 補正条件 | 追加 | `enabled`: bool、`statistic`: `median`/`mean`、`exclude_above`・`exclude_below`: 整数、`min_gain`・`max_gain`: 数値。各項目省略可 | `true`、`median`、230、0、0.5、2.0。下限 < 上限、0 < 最小倍率 <= 最大倍率、有限数 | 設定読込み | 不正値は処理前に拒否 |
| 分割画像 | 変更 | 既存のBGR 8bit画像と同じ保存形式 | 有効時に画素を補正。補正不能時は元画素 | 学習・試験準備 | 旧画像は再生成 |
| 準備manifestの指紋 | 変更 | 既存の文字列形式 | 常に有効・無効を区別。有効時は既定値を展開した全6項目を含める。無効時は `enabled=false` のみを含める | 指紋生成 | 旧指紋との互換性なし |

## インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 型番設定の読込み | 既存CLI → 共通設定 | 補正オブジェクト | 既定値を含む設定 | 不正型・値・関係 → 項目を示す入力不備、成果物不変 | 設定を直して再実行 |
| `train-pre` | 運用者 → 画像準備 | 有効な設定と学習元画像 | グループ別補正画像と指紋 | 既存の読込み・範囲・位置合わせ失敗契約を適用 | 既存の段階公開。新条件で再実行 |
| `test-pre` | 運用者 → 画像準備 | 有効な設定と試験元画像 | 全分割の補正画像と指紋 | 既存の読込み・範囲・未判定契約を適用 | 既存の段階公開。新条件で再実行 |
| 補正計算 | 準備処理 → 画像計算 | 対象と基準の分割画像 | 補正後の画素 | 値なし・対象値0以下 → 補正前画素。処理失敗は段階公開前に中止 | 同じ入力なら同じ画素 |

## 技術判断

### 判断・候補: 輝度統計と倍率計算

- **状態**: 確定。
- **採用内容 / 候補**: OpenCVのBGR→GRAY変換後に、`exclude_below <= gray < exclude_above` の画素へNumPyのmedianまたはmeanを適用する。目標÷対象を上下限で挟み、全BGRチャンネルを浮動小数へ変換して倍率を掛け、`floor(value + 0.5)` の後に0～255へ収めて8bitへ戻す。
- **根拠**: 既存画像入力はOpenCVによるBGRの8bit配列であり、要件の統計・四捨五入を再現できる。
- **代替案**: `np.rint` は0.5を偶数へ丸める場合があるため採用しない。グレースケール画像だけの補正では色チャンネルの倍率が一致しないため採用しない。
- **実装規則 / 不変条件**: マスクの画素が0件なら「値なし」。対象値が0以下なら除算しない。補正前配列を変更しない。目標値0は有効値として倍率下限を適用する。
- **影響**: 画像ごとにグレースケール変換と集計が増える。数値性能目標は合意されていない。

### 判断・候補: 基準分割と処理順

- **状態**: 確定。
- **採用内容 / 候補**: 既存の `scaled_crop_range` と `crop_image` を基準と位置合わせ済み画像の双方に使う。補正は分割後、ファイル保存前に適用する。
- **根拠**: 分割座標の丸めとサイズを既存契約と一致させ、位置合わせ自体へ輝度補正を影響させない。
- **代替案**: 元画像または画像全体の補正は分割ごとの目標値を満たさないため採用しない。
- **実装規則 / 不変条件**: 基準分割は縮小済みの基準画像から取る。学習のブラックリスト分割には補正計算をしない。重複グループの同じ分割は同じ画素とする。
- **影響**: 基準の範囲外は既存の準備失敗経路に従う。

### 判断・候補: 無効時の指紋

- **状態**: 確定。
- **採用内容 / 候補**: `enabled` は常に指紋へ含める。有効時は残る5項目も含める。無効時は画素へ影響しない残る項目を指紋へ含めない。
- **根拠**: 有効・無効の切替を区別し、補正を使わない間の無関係な設定変更による再準備を避ける。ユーザー指定の「有効な場合は全項目」を満たす。
- **代替案**: 無効時も全項目を含める方式は画素が同じでも指紋が変わるため採用しない。
- **実装規則 / 不変条件**: 既定値を展開してから指紋化し、明示値と省略値が同じなら同じ指紋とする。
- **影響**: 旧準備指紋は再使用できない。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 閾値が同値・逆転、倍率が逆転、非有限数、型違い | 共通設定 | 準備前に拒否、旧成果物保持 | 項目名を示す入力不備 | 既存CLIの標準エラーと終了コード2 | 設定を修正して再実行 |
| 除外後の対象・基準画素が0件、対象輝度0 | 画像計算 | 該当分割のみ補正しない | 分割画像は保存される | 新しい警告・未判定区分は増やさない | 必要なら撮影・条件を確認 |
| 補正中の予期しない処理失敗 | 準備処理 | 段階公開前に中止、旧成果物保持 | 既存の処理失敗 | 既存CLIの標準エラー | 原因を直して準備を再実行 |
| 条件変更後の旧準備結果 | 後続の既存照合 | 利用を拒否 | 指紋不一致と準備再実行案内 | 既存のエラー経路 | 準備・学習・検査を再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 整数は真偽値・小数を拒否し、倍率は正の有限数を要求する | TC-002の境界値で確認 |
| 性能 | 分割画像ごとに集計と乗算を一回行う。新しい時間上限は設定しない | 品質検査で機能退行を確認。対象OSで処理時間を証跡に記録 |
| 運用 | 新しい設定で全準備・学習・検査を再実行する | AC-005で対象OSと成果物読戻しを確認 |

認証・認可と外部通知は追加しないため、既存のローカルCLI境界を適用する。

## 移行とロールバック

1. 変更後の型番設定を確認し、旧成果物を引き継がず `check` (分割確認が必要な場合)、`train-pre`、`train`、`test-pre`、`test` の順に再実行する。<br />
   準備指紋不一致または旧形式の成果物は使わない。
2. 完了判定は新条件の学習・試験manifest、checkpoint、検査結果が整合して読めることとする。
3. ロールバック時は旧コード・旧設定と、それに対応する旧成果物一式へ戻す。<br />
   新旧成果物の混在利用はしない。旧一式を保持していない場合は旧環境で再生成する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-027 | REQ-027-S01 | unit / integration | 補正設定全体・一部を省略して読込み、準備 | 既定値が適用され両準備へ反映 | `tests/test_config.py::test_brightness_defaults` | はい | 設定モデルと既定値 | 対象OSのCLI確認 (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-002 | REQ-027 | REQ-027-S02 | unit / integration | 不正型、範囲端、逆転、非有限数を設定してCLI起動 | 項目名付き入力不備、旧成果物保持 | `tests/test_config.py::test_brightness_rejects_invalid_settings` | はい | 検証と既存CLIの失敗契約 | 対象OSのCLI確認 (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-003 | REQ-028 | REQ-028-S01 | unit / integration | 値を制御したBGR画像でmedian・mean・除外範囲を指定し、両準備を実行 | 縮小基準の同じ範囲に基づく保存画素。元画像保持 | `tests/test_preparation.py::test_brightness_normalizes_train_and_test_splits` | はい | 実OpenCV・NumPy、整列テストダブル、PNG保存 | 実画像・対象OS (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-004 | REQ-028 | REQ-028-S02 | unit | 比率の上下限と0.5境界・飽和を持つ画像を補正 | 期待する画素値へ四捨五入・飽和 | `tests/test_preparation.py::test_brightness_gain_and_rounding_boundaries` | はい | 画素計算 | 実画像・対象OS (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-005 | REQ-028 | REQ-028-S03 | unit / integration | 基準または対象に有効画素なし、対象値0で準備 | 元画素を保存、他分割は準備 | `tests/test_preparation.py::test_brightness_skips_unavailable_statistics` | はい | 画素計算と分割単位の継続 | 実画像・対象OS (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-006 | REQ-028 | REQ-028-S04 | integration | `enabled=false` で両準備 | 保存画像は補正前と一致 | `tests/test_preparation.py::test_brightness_disabled_preserves_splits` | はい | 学習・試験の保存画像 | 対象OSのCLI確認 (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-007 | REQ-025 | REQ-025-S01 | integration | 補正有効でグループ指定の学習準備 | 対象グループのmanifestに一致する指紋 | `tests/test_config.py::test_brightness_training_fingerprint` | はい | 学習指紋とmanifest | 対象OSの再実行 (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-008 | REQ-025 | REQ-025-S02 | integration | 補正有効で試験準備後、ブラックリスト・学習条件を変更 | 試験manifest指紋は一致 | `tests/test_config.py::test_brightness_testing_fingerprint` | はい | 試験指紋と除外項目 | 対象OSの再実行 (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |
| TC-009 | REQ-025 | REQ-025-S03 | integration | 有効時の各項目と有効・無効を変更し、旧manifestを学習・検査に渡す | 両指紋が変化し旧結果は拒否 | `tests/test_config.py::test_brightness_changes_invalidate_preparation` | はい | 指紋変化と後続の既存照合 | 対象OSの再実行 (3.5) | openspec/changes/archive/2026-10-22-add-brightness-normalization/evidence/implementation.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-027 | 2 | 2 | なし | 網羅 |
| REQ-028 | 4 | 4 | なし | 網羅 |
| REQ-025 | 3 | 3 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | Ubuntu 24.04 LTS・Windows 11でmedian・mean・無効化の学習・試験準備画像 | TC-003、TC-004、TC-006と対象OSでの分割画像読戻し | 実装・自動試験と対象OS確認 (3.1～3.5) | 未検証 | 未作成 |
| AC-002 | 両OSで値なし・対象値0の分割が補正前画素で保存される | TC-005と対象OSでの補正不能例の読戻し | 実装・自動試験と対象OS確認 (3.2、3.5) | 未検証 | 未作成 |
| AC-003 | 両OSのCLIで不正設定を入力し、既存準備成果物を保持 | TC-002と対象OSの終了コード・保存先確認 | 実装・自動試験と対象OS確認 (3.1、3.5) | 未検証 | 未作成 |
| AC-004 | 両OSで有効時の全項目を変更し、学習・試験指紋と旧成果物拒否を確認 | TC-007～TC-009と対象OSの再実行 | 実装・自動試験と対象OS確認 (3.3、3.5) | 未検証 | 未作成 |
| AC-005 | 両OSのCPUと利用可能なGPUで新条件の準備・学習・検査、成果物読戻し | `scripts/run_visual_inspection_smoke.py` の全件・単独グループを実行して証跡を確認 | 対象OSの実機確認 (3.5) | 未検証 | 未作成 |
