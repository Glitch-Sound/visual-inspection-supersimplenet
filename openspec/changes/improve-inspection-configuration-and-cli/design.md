## 背景・前提

現在 `src/app/image_preparation/preparation.py` は基準画像と元画像を縮小して位置合わせし、縮小後の `range` 座標で切り出す。`src/app/model_evaluation/evaluation.py` は型番設定、checkpoint、最良試行結果の暫定閾値を照合してから判定する。`src/app/common/cli.py` は標準出力に終了時 JSON を1件出す。型番設定と学習成果物の更新は別の処理境界にあり、検査用上書き値で学習成果物を書き換えない。

## 目標・対象外

### 目標

- 元画像座標を一意に縮小後座標へ換算し、`check` と学習・試験準備の対象を揃える。
- 暫定閾値の整合検査と検査用判定閾値の選択を分離する。
- 人向けの進行表示と既存の標準出力 JSON 契約を両立する。

### 対象外

- 学習スコアの算出、Optuna 探索、モデル構造と検査用閾値の自動調整。
- 既存の縮小後 `range` を自動判別して変換すること。設定形式に版情報がないため、旧値を安全に識別できない。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | 座標換算、試験設計 | 範囲確認 | 1.1, 1.3, 3.1 | TC-001〜TC-004 | 確認画像と入力拒否 |
| REQ-002 | 座標換算、画像準備 | 学習準備 | 1.1, 1.2, 3.1 | TC-005〜TC-010 | 分割画像とmanifest、失敗時保全 |
| REQ-003 | 座標換算、画像準備 | 試験準備 | 1.1, 1.2, 3.1 | TC-011〜TC-014 | 分割画像とmanifest、未判定 |
| REQ-017 | 実行表示 | 準備進捗 | 2.2, 3.2 | TC-015〜TC-016 | 件数、失敗時表示 |
| REQ-018 | 閾値契約 | 評価設定と判定 | 2.1, 2.3, 3.3 | TC-017〜TC-022 | 判定、結果JSON、整合拒否 |
| NREQ-002 | 実行表示 | 共通CLI | 2.2, 3.2 | TC-023〜TC-024 | 5 CLI、終了記録、終了コード |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 確定した配置 |
| --- | --- | --- | --- | --- | --- |
| 型番設定 | 追加 | `part_<model>.json` | 検査用閾値、既存の暫定閾値と `range` | なし | `src/app/common/config.py` |
| 座標換算 | 変更 | `range`、`IMAGE.RESIZE` | 縮小後の整数座標 | 設定 | `src/app/image_preparation/imaging.py` |
| 確認・準備 | 変更 | 基準画像、元画像、換算座標 | 確認画像、分割画像、manifest | 共通画像I/O | `src/app/image_preparation/preparation.py` |
| 判定 | 変更 | 検査設定、学習成果物、スコア | 判定、結果JSON | 共通成果物契約 | `src/app/model_evaluation/evaluation.py` |
| 実行表示 | 追加 | コマンド、段階、進捗、警告・エラー | stderr の人向け表示、stdout の終了 JSON | `RunRecorder` | `src/app/common/cli.py` と各能力の CLI |

### 処理フロー

1. 共通設定は `IMAGE.SIZE` と `IMAGE.RESIZE` を読み、型番設定は元画像基準の非負整数 `range.x`・`range.y` と、任意の検査用閾値を検証する。
2. `check`、`train-pre`、`test-pre` は同じ換算規則で座標を縮小後画像へ写し、縮小後の `SIZE` ピクセル四方を対象にする。基準画像の確認表示は縮小後画像上に換算後の矩形を描く。
3. 準備コマンドは対象元画像を列挙して総数を確定し、各画像の成功、除外、未判定または失敗が確定するごとに処理済み数を更新する。既存のステージングと一式置換は維持する。
4. `train` は従来どおり学習由来の暫定閾値のみを更新する。検査用閾値は型番設定の独立した項目として保持し、学習成果物へ複写しない。
5. `test` は暫定閾値と checkpoint・最良試行結果の一致を検証してから、有効な上書き値または暫定値を選択する。選択値で全分割を判定し、元画像の結果 JSON の `threshold` に保存する。
6. すべての CLI は段階と結果を人向けに表示し、最後に既存形式の実行記録 JSON を標準出力へ1件出す。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番設定 | 追加 | `inspection_threshold: number or null` (任意) | 0〜1、未指定と `null` は暫定閾値 | 評価者 | 旧設定は未指定として読める |
| 型番設定 | 意味変更 | `range[].x/y: nonnegative integer` | 縮小前の基準画像座標 | 運用者 | **BREAKING** 旧値は手動で再確認 |
| 共通設定 | 維持 | `IMAGE.SIZE: positive integer`, `IMAGE.RESIZE: (0,1]` | `SIZE` は縮小後の切り出し辺長 | 運用者 | 値の意味は維持 |
| 学習成果物 | 維持 | checkpoint・best_trial・`optuna_settings.threshold.value` | 三者の暫定閾値が一致 | 学習 | 検査用閾値を含めない |
| 検査結果 JSON | 意味明確化 | `threshold: number` (必須) | 実際の判定に使用した値 | 評価 | 既存キーを維持 |
| CLI 出力 | 維持・追加 | stdout の終了 JSON 1件、stderr の人向け表示 | 終了コード0/2/3を維持 | 各CLI | JSON利用者は stdout を継続利用 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 再試行 |
| --- | --- | --- | --- | --- | --- |
| `check` | 運用者 → 画像準備 | 型番、座標、倍率 | 確認画像とそのパス | 換算後に範囲外 → 入力不備、旧確認画像を保持 | 座標修正後に再実行 |
| `train-pre` / `test-pre` | 運用者 → 画像準備 | 元画像、型番設定 | 分割画像、manifest、進捗 | 読込み不能 → 処理失敗、旧一式を保持。位置合わせ失敗 → 除外または未判定 | 入力修正後に再実行 |
| `train` | 運用者 → 学習 | 準備画像と設定 | 暫定閾値と学習成果物 | 既存の失敗契約を維持 | 既存の再開・`--restart` |
| `test` | 運用者 → 評価 | 暫定・検査用閾値、成果物 | 判定と使用閾値 | 無効値・暫定閾値不一致 → 入力不備、推論しない | 設定・成果物修正後に再実行 |

## 技術判断

### 判断1: 座標換算

- **状態**: 確定。
- **採用内容**: 非負整数の元画像座標について `floor(座標 × RESIZE + 0.5)` で縮小後の左上座標を得る。`RESIZE = 1` では元の座標を維持する。
- **根拠**: 利用者が確認した `400 × 0.5 = 200` を満たし、端数の結果を再現できる。
- **代替案**: 元画像から切り出してから出力を再拡大する方式は、縮小後から `SIZE` 四方を切り出す合意と異なる。
- **実装規則 / 不変条件**: 確認・学習準備・試験準備で同じ関数を使い、換算後に縮小画像の寸法と `SIZE` で範囲を検証する。負座標や範囲外を丸めで救済しない。
- **影響**: 旧 `range` 値の意味が変わるため移行が必要。

### 判断2: 検査用閾値

- **状態**: 確定。
- **採用内容**: `inspection_threshold` を `optuna_settings` の外側に置く。JSON 数値の整数・小数は受け入れ、真偽値、文字列、非有限値、範囲外を拒否する。
- **根拠**: 暫定閾値の生成・整合契約を維持しながら検査の判定境界を変えられる。
- **代替案**: `optuna_settings.threshold.value` の手動変更は checkpoint と最良試行結果の整合を壊すため採用しない。
- **実装規則 / 不変条件**: 成果物一致検査は暫定値だけに対して行う。学習の一式更新で上書き値を保存したままにする。結果 JSON の既存 `threshold` は実効値とする。
- **影響**: 同じモデルでも検査用閾値によって判定が変わるため、結果の使用値を確認する。

### 判断3: 実行表示

- **状態**: 確定。
- **採用内容**: stdout は1件の JSON 終了記録に限定し、人向けの状態・警告・進捗は stderr に出す。TTY では既存依存の Rich の進捗バーを用い、非TTYでは件数を示す行形式にする。
- **根拠**: `tests/test_runtime.py` などが stdout の JSON を契約として使用している。Rich は既に依存にある。
- **代替案**: stdout に進捗を混在させる方式は既存の JSON 消費側を壊す。
- **実装規則 / 不変条件**: 実行記録のフィールドと終了コードを維持する。失敗時も進捗を閉じ、完了していない件数を成功件数と誤表示しない。
- **影響**: stderr を収集する利用者には追加行が見える。個別画像名と失敗理由は警告・エラーに残す。

人向け表示は、型番とコマンド名を開始時に示し、次の段階と終了要約をコマンドごとに示す。警告は対象画像と理由、エラーは対象項目または画像と理由を示す。内部の例外名だけを終了要約にしない。

| コマンド | 処理段階の表示 | 成功時の要約 |
| --- | --- | --- |
| `check` | 設定読込、基準画像・範囲確認、確認画像保存 | 確認画像のパスと範囲数 |
| `train-pre` | 対象画像の列挙、位置合わせ・切り出し、manifest 保存 | 対象数、準備数、除外数、保存先 |
| `train` | 学習入力の確認、探索、最良試行の成果物保存 | 試行数、暫定探索指標、暫定閾値、保存先 |
| `test-pre` | 対象画像の列挙、位置合わせ・切り出し、manifest 保存 | 対象数、準備数、未判定数、保存先 |
| `test` | 学習成果物の照合、閾値の選択、推論・結果保存 | 元画像の正常・異常・未判定件数、使用閾値とその出所、保存先 |

非TTYでは `train-pre`・`test-pre` の対象数と処理済み数を改行区切りで出し、TTYでは同じ数値を進捗バーへ反映する。対象数0でも除算せず `0/0` と表示し、成功件数0であることを終了要約へ示す。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 換算後に範囲外 | 画像準備 | 対象実行を中止、旧成果物を維持 | ID・座標・画像寸法を示す | JSON エラーと stderr | `range` を修正して再実行 |
| 検査用閾値が不正 | 設定 | 推論を開始しない | 項目と値の条件を示す | 入力不備の終了記録 | 設定修正後に再実行 |
| 暫定閾値が不一致 | 評価 | 推論を開始しない | 不一致対象を示す | 入力不備の終了記録 | 学習成果物を一式確認 |
| 位置合わせ失敗 | 画像準備 | 学習は除外、試験は未判定 | 対象画像と理由 | manifest、警告 | 再確認または再撮影 |
| 準備途中の画像I/O失敗 | 画像準備 | ステージを破棄、旧一式を保持 | 失敗対象と未完了状態 | stderr と終了記録 | 原画像修正後に再実行 |
| `test --restart` の検査前不整合 | 既存の再検査 CLI | 現行実装は旧結果を削除してから最良試行と checkpoint を照合する | 不一致なら新結果なしで終了する | 終了記録 | 旧結果が必要なら再検査前に退避し、成果物を修正して再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 秘密情報 | 画像内容や環境変数をログへ出さず、型番・ファイル名・理由に限定する | 出力レビュー |
| 処理時間 | 進捗の更新を元画像単位にし、画像・分割ごとの描画更新を避ける | 対象環境での準備実行時間を記録 |
| 運用 | 新旧座標で得る切り出し位置と画像内容を照合する | 同じなら既存成果物の利用可否を記録し、異なる場合は再生成した成果物を記録 |

## 移行とロールバック

1. `part_<model>.json` の既存 `range` と派生成果物をバックアップし、旧縮小後座標に対応する縮小前の整数座標を記入する。`floor(新座標 × RESIZE + 0.5)` が各旧座標と一致すること、`SIZE` と `RESIZE` が変わっていないことを確認する。端数と画像端は `check` の確認画像で目視確認する。
2. 学習・試験準備を再実行し、旧分割画像と新分割画像の画素内容、manifest の元画像と分割 ID の対応を比較する。一致する場合は既存モデルの利用可否を記録できる。不一致または確認不能なら、新しい準備画像に対して `train --restart` で学習し直し、続いて `test` を再実行する。必要な旧成果物は実行前に退避する。
3. `test --restart` は現行実装で旧結果を先に削除するため、旧結果が必要なら実行前に退避する。ロールバック時は旧コード、退避した旧設定、旧準備画像・checkpoint・最良試行結果・検査結果を一式で戻す。新旧の派生成果物を混用しない。

## 試験設計

以下の各 TC は同名の pytest 関数で自動試験する。検証範囲は固定画像またはテストダブルによる契約であり、対象 OS の実機表示と画像内容の目視確認は受け入れタスクで別途行う。自動試験の実行結果は `evidence/acceptance.md` に記録する。

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-001 | REQ-001-S01 | integration | 型番の基準画像、正の整数である画像サイズ、有効な縮小倍率、一意な分割 ID、および縮小前の基準画像で指定し、換算後に縮小後の画像内に収まる左上座標が設定されている。運用者が `check --model <型番>` を実行する | システムは縮小前座標を換算した縮小後の基準画像上に各分割範囲の矩形と ID を描いた型番別の確認画像を保存する | `tests/test_preparation.py::test_change_req_001_01` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-002 | REQ-001 | REQ-001-S02 | integration | 換算後の分割範囲が縮小後の基準画像外にはみ出す、分割 ID が重複する、画像サイズが整数でないか正でない、縮小倍率が0以下・1超・非数値の設定がある、または有効な倍率でも基準画像の縮小後の縦横いずれかが0ピクセルとなる。運用者が `check --model <型番>` を実行する | システムは対象の設定項目または画像と理由を示して処理をエラー終了する。縮小不能な画像は処理失敗、設定と範囲の不備は入力不備として扱う | `tests/test_preparation.py::test_change_req_001_02` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-003 | REQ-001 | REQ-001-S03 | integration | 型番設定の `base` に絶対パス、`.`、`..`、パス区切り文字を含む値、または学習元画像の型番別ルート外へ解決される値が指定されている。運用者が当該型番のコマンドを実行する | システムは `base` が安全なファイル名ではないことを示して処理開始前にエラー終了する | `tests/test_preparation.py::test_change_req_001_03` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-004 | REQ-001 | REQ-001-S04 | integration | `RESIZE = 0.5`、`SIZE = 500`、縮小前基準画像で `x = 400` と `x = 401` の異なる分割 ID がある。運用者が `check --model <型番>` を実行する | 縮小後画像の `x = 200` と `x = 201` にそれぞれ `SIZE` 四方の矩形と分割 ID を描く | `tests/test_preparation.py::test_change_req_001_04` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-005 | REQ-002 | REQ-002-S01 | integration | 有効な型番設定と、縮小後に設定した対応点条件で位置合わせ可能な学習元画像がある。運用者が `train-pre --model <型番>` を実行する | システムは基準画像と元画像を指定倍率で縮小して位置合わせした各画像から、縮小前座標を指定倍率で換算した開始位置から `SIZE` ピクセル四方の全分割範囲を切り出し、`<元画像名>_<2桁分割ID>.<元拡張子>` の名称で型番別学習領域へ保存する | `tests/test_preparation.py::test_change_req_002_01` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-006 | REQ-002 | REQ-002-S02 | integration | 学習元画像名と分割 ID の組み合わせが型番のブラックリストに指定されている。運用者が学習準備を実行する | システムは該当する分割画像を学習領域へ保存しない | `tests/test_preparation.py::test_change_req_002_02` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-007 | REQ-002 | REQ-002-S03 | integration | 学習元画像が最低マッチ数、ホモグラフィ推定、または最低インライア比率のいずれかを満たさず、基準画像へ位置合わせできない。運用者が学習準備を実行する | システムは該当する元画像の全分割を学習対象から除外する | `tests/test_preparation.py::test_change_req_002_03` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-008 | REQ-002 | REQ-002-S04 | integration | 位置合わせ後の学習画像に対して分割範囲が画像外にはみ出す。運用者が学習準備を実行する | システムは元画像名と分割 ID を示して処理をエラー終了する | `tests/test_preparation.py::test_change_req_002_04` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-009 | REQ-002 | REQ-002-S05 | integration | 型番の学習元画像を画像として読み込めない。運用者が学習準備を実行する | システムは対象の元画像名を示して処理失敗としてエラー終了する | `tests/test_preparation.py::test_change_req_002_05` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-010 | REQ-002 | REQ-002-S06 | integration | `knn_k` が2でない、または `ratio_threshold` が0以下・1以上・非数値である。運用者が学習準備を実行する | システムは不正な設定項目を示して処理開始前にエラー終了する | `tests/test_preparation.py::test_change_req_002_06` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-011 | REQ-003 | REQ-003-S01 | integration | 有効な型番設定と、縮小後に設定した対応点条件で位置合わせ可能な試験元画像がある。運用者が `test-pre --model <型番>` を実行する | システムは基準画像と元画像を指定倍率で縮小して位置合わせした各画像から、縮小前座標を指定倍率で換算した開始位置から `SIZE` ピクセル四方の全分割範囲を切り出し、`<元画像名>_<2桁分割ID>.<元拡張子>` の名称で型番別試験領域へ保存する | `tests/test_preparation.py::test_change_req_003_01` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-012 | REQ-003 | REQ-003-S02 | integration | 試験元画像が最低マッチ数、ホモグラフィ推定、または最低インライア比率のいずれかを満たさず、基準画像へ位置合わせできない。運用者が試験準備を実行する | システムは該当元画像を正常な分割画像一式として保存しない | `tests/test_preparation.py::test_change_req_003_02` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-013 | REQ-003 | REQ-003-S03 | integration | 位置合わせ後の試験画像に対して分割範囲が画像外にはみ出す。運用者が試験準備を実行する | システムは元画像名と分割 ID を示して処理をエラー終了する | `tests/test_preparation.py::test_change_req_003_03` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-014 | REQ-003 | REQ-003-S04 | integration | 型番の試験元画像を画像として読み込めない。運用者が試験準備を実行する | システムは対象の元画像名を示して処理失敗としてエラー終了する | `tests/test_preparation.py::test_change_req_003_04` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-015 | REQ-017 | REQ-017-S01 | integration | 複数の学習または試験元画像がある。運用者が `train-pre` または `test-pre` を実行する | システムは対象画像数と処理済み数を進行に合わせて表示し、終了時には処理結果を示す | `tests/test_preparation.py::test_change_req_017_01` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-016 | REQ-017 | REQ-017-S02 | integration | 準備途中に読み込み不能な元画像がある。運用者が `train-pre` または `test-pre` を実行する | システムは失敗した画像と理由、完了していない状態を示し、処理済み件数を成功件数として表示しない | `tests/test_preparation.py::test_change_req_017_02` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-017 | REQ-018 | REQ-018-S01 | integration | 暫定閾値と整合する学習成果物があり、検査用閾値を指定していない。運用者が `test --model <型番>` を実行する | システムは暫定閾値で分割画像を判定し、結果にその使用値を記録する | `tests/test_evaluation.py::test_change_req_018_01` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-018 | REQ-018 | REQ-018-S02 | integration | 有効な暫定閾値があり、検査用閾値が `null` である。運用者が検査を実行する | システムは暫定閾値で判定し、結果にその使用値を記録する | `tests/test_evaluation.py::test_change_req_018_02` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-019 | REQ-018 | REQ-018-S03 | integration | 暫定閾値と異なる0以上1以下の検査用閾値がある。運用者が検査を実行する | システムは指定した閾値で判定し、結果にその使用値を記録する | `tests/test_evaluation.py::test_change_req_018_03` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-020 | REQ-018 | REQ-018-S04 | integration | 検査用閾値が0または1である。運用者が検査を実行する | システムはその値を判定に使用し、スコアが使用閾値に等しければ `anomaly` と記録する | `tests/test_evaluation.py::test_change_req_018_04` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-021 | REQ-018 | REQ-018-S05 | integration | 検査用閾値が0未満、1超、数値以外、または真偽値である。運用者が検査を実行する | システムは設定項目と理由を示して推論前に入力不備として拒否し、不完全な検査結果を正常な結果として保存しない | `tests/test_evaluation.py::test_change_req_018_05` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-022 | REQ-018 | REQ-018-S06 | integration | 検査用閾値が有効でも、型番設定・checkpoint・最良試行結果の暫定閾値が一致しない。運用者が検査を実行する | システムは不一致を示して推論前に拒否し、成果物の確認を促す | `tests/test_evaluation.py::test_change_req_018_06` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-023 | NREQ-002 | NREQ-002-S01 | integration | 有効な入力で5 CLIをそれぞれ実行し、準備2 CLIはTTY・非TTYを切り替える | コマンド別の段階と終了要約、準備件数、stdout の JSON 1件、終了コード0を確認できる | `tests/test_runtime.py::test_change_nreq_002_01` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| TC-024 | NREQ-002 | NREQ-002-S02 | integration | 設定不備、位置合わせ失敗、または処理失敗で該当 CLI を実行する | 対象、理由、未完了状態、警告とエラーの区別、stdout の JSON 1件と終了コードを確認できる | `tests/test_runtime.py::test_change_nreq_002_02` | はい | 固定入力とCLI契約 | 対象OS・実画像の受け入れ確認 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-001 | 4 | 4 | なし | 網羅 |
| REQ-002 | 6 | 6 | なし | 網羅 |
| REQ-003 | 4 | 4 | なし | 網羅 |
| REQ-017 | 2 | 2 | なし | 網羅 |
| REQ-018 | 6 | 6 | なし | 網羅 |
| NREQ-002 | 2 | 2 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 暫定・指定値の判定と学習成果物の整合 | 閾値の自動試験と結果確認 | 対象 OS・実モデルでの確認 | 未検証 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| AC-002 | 不正値の拒否と使用値の記録 | 型番設定と結果 JSON の試験 | なし | 検証済み | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| AC-003 | 5 CLI の可読性、進捗、JSON・終了コード | CLI 自動試験と Ubuntu・Windows 実機表示 | Ubuntu・Windows 実機確認 | 未検証 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| AC-004 | 原座標と縮小後の `SIZE` 切り出し | 固定画像の自動試験と `check` 目視 | 対象型番の実画像確認 | 未検証 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| AC-005 | 設定不備と失敗時の保全・未判定 | 例外試験と成果物確認 | 対象環境での失敗分岐確認 | 未検証 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
| AC-006 | 旧座標の換算と画像一致の確認、差異がある場合の派生成果物再生成 | README 手順レビューと対象型番での画像比較・必要時の再学習 | 対象型番の旧画像と成果物の比較 | 未検証 | `openspec/changes/improve-inspection-configuration-and-cli/evidence/acceptance.md` |
