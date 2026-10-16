## 背景・前提

現行の `SyntheticValidationSettings` は `types`、単一 `intensity`、`seed` を持つ。<br />
`synthetic_validation.py` は検証分割画像1枚につき擬似画像1枚を生成し、欠陥寸法を画像辺長と強度から計算する。<br />
`search.py` は AUROC と正常スコアの99パーセンタイルを各試行へ記録し、`cli.py` と `artifacts.py` は `study.best_trial` を参照する。<br />
最良試行結果は `BestTrialResult` に保存し、既存の成果物トランザクションで公開する。<br />
進行中の `fix-gpu-determinism-and-refit-threshold` は同じ学習経路の決定論設定と閾値の出所を扱うため、本変更ではその境界を維持し、閾値算出元を変更しない。

## 目標・対象外

### 目標

- 検証分割画像ごとに画素数・強度の範囲から指定枚数を再現可能に生成する。
- 旧設定では生成画像、目的値、正常百分位目的の選択規則を維持する。
- 擬似 AUROC 同点時の選択を探索後・成果物保存時・再開時に一貫させる。
- 上限到達の正常完了試行数を保存・警告し、旧結果の未記録状態と区別する。

### 対象外

- 実異常での精度目標の設定と、その目標を満たす欠陥寸法の自動推定。実画像による評価を別途要する。
- 既存探索履歴の試行・成果物の書換え。評価条件を変えた対象グループは `train --restart` を使う。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-005 | 処理フロー、試行選択 | 探索→学習CLI→保存 | 2.1、2.2 | TC-001〜TC-004 | 同点・通常・旧設定の試行選択をテストダブルで確認 |
| REQ-007 | データ契約と状態、処理フロー | 探索結果→成果物・警告 | 2.2、3.1 | TC-005〜TC-011 | JSON読戻し、警告、既存成果物の契約を確認 |
| REQ-030 | データ契約と状態、擬似画像生成 | 型番設定→検証画像 | 1.1、1.2 | TC-012〜TC-015 | 4種類・範囲・枚数・互換・不正設定を確認 |
| REQ-039 | 技術判断、運用 | 雛形・README→運用者 | 3.2 | TC-016 | 雛形の読込と案内を確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 擬似検証設定 | 変更 | 型番設定JSON | 検証済み条件 | `train` | `app.common.config` で確定。学習・保存で共有する設定契約のため |
| 擬似画像生成 | 変更 | 検証分割画像、条件、seed | 一時的な擬似画像列 | 設定契約 | `app.model_training.synthetic_validation` で確定。学習能力の検証入力だけを作るため |
| 探索指標・最良試行 | 変更 | 正常・擬似スコア、完了試行 | 選択済み試行、上限到達件数 | Optunaの試行履歴 | `app.model_training.search` に選択関数を集約する。CLI・保存が同じ関数を使う |
| 結果保存と警告 | 変更 | 選択済み試行、履歴 | 最良試行JSON、CLI警告 | 既存成果物トランザクション | `app.model_training.artifacts`、`cli`、共有結果型で確定 |
| 雛形と運用案内 | 変更 | 初期設定例、残り誤差 | 型番設定例、READMEの調整手順 | 運用者の実測 | `config/part_XX.json` と `README.md` で確定 |

### 処理フロー

1. `train` が型番設定を読む。<br />
   画素範囲、強度範囲、枚数を検証し、不正なら探索・成果物更新前に拒否する。
2. 検証分割画像を元の順で走査し、各画像から指定枚数を一時領域へ生成する。<br />
   新方式の乱数種は設定seed、グループ、元ファイル名、複製番号から決め、同じ入力で同じ種類・寸法・強度・位置となる。<br />
   旧設定では従来の乱数種、生成計算、ファイル名をそのまま使う。
3. 各試行は正常スコアと全擬似スコアから既存の AUROC を計算し、正常スコアの99パーセンタイルとともに保存する。<br />
   擬似スコアが空または非有限なら試行を失敗とし、選択対象から除く。
4. 探索終了後、`synthetic_auroc` では正常完了試行を `(-AUROC, 正常p99, 試行番号)` の順に比較する。<br />
   `normal_percentile` は従来の `study.best_trial` を使う。<br />
   選択済み試行の条件を全件再学習へ渡し、保存時にも同じ選択関数を使う。
5. `synthetic_auroc` の正常完了試行から `value == 1.0` を数え、最良試行JSONへ書く。<br />
   件数が1以上ならCLIの警告と実行記録へ入れる。<br />
   旧結果の件数未記録は `null` として読めるようにする。
6. 運用者は生成条件と上限到達数を確認し、必要なら条件を変更して `train --restart` を実行する。<br />
   実異常の評価は別に行う。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| `synthetic_validation` | 追加 | `size_px: {min: int, max: int} | null` (任意) | 1以上、min≤max。欠陥の長さ・直径・一辺。省略時は従来の辺長依存式 | 設定読込 | 旧設定は省略可 |
| 同上 | 追加 | `intensity_range: {min: float, max: float} | null` (任意) | 0<min≤max≤1。既存の明示的 `intensity` と同時指定を拒否 | 設定読込 | 省略時は従来の単一 `intensity`、既定0.5 |
| 同上 | 追加 | `images_per_validation_image: int` (任意) | 1以上、既定1 | 設定読込 | 旧設定は1枚 |
| `evaluation_contract` | 変更 | 上記の有効条件 | 既存履歴の旧形式は新項目の省略値とだけ同等とみなす | 探索作成 | 条件が変われば `train --restart` |
| 最良試行結果 | 追加 | `synthetic_auroc_ceiling_trial_count: int | null` | `synthetic_auroc` の新結果では0以上。旧結果・`normal_percentile` は `null` | 成果物保存 | 旧結果を推測で埋めない |

画素範囲の抽選は両端を含む整数一様分布、強度範囲は両端を許す連続一様分布とする。<br />
範囲の最小と最大が同じ場合は固定値となる。<br />
分割画像より大きい指定寸法は画像内に収まる寸法へ制限し、小画像でも空の擬似画像にしない。<br />
正常画像は1枚のまま、擬似画像だけを指定倍数にするため、AUROC は全正常スコアと全擬似スコアの組で計算する。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train` 設定読込 | 運用者 → CLI | 新旧の擬似検証条件 | 検証済み条件 | 範囲逆転・0・競合 → 項目と理由を表示し旧成果物保持 | 修正して再実行 |
| 擬似画像生成 | CLI → 学習 | 分割画像、条件、seed | 指定枚数の一時画像 | 画像読込・保存失敗 → 試行失敗、旧成果物保持 | 同条件・同環境なら再現 |
| 最良試行の選択 | CLI・保存 → 探索 | 完了試行の AUROC・p99・番号 | 単一の選択試行 | 有効試行なし・p99欠落 → 理由を示して成果物更新しない | 条件修正または `--restart` |
| 結果公開 | 保存 → 運用者 | 最良試行と件数 | JSON・警告・checkpoint | 書込み失敗 → 既存一式復旧 | 既存トランザクションを使用 |

## 技術判断

### 判断・候補: 旧設定と新しい範囲指定

- **状態**: 確定。
- **採用内容 / 候補**: `size_px` と `intensity_range` は独立した任意項目にする。既存 `intensity` は残し、範囲との明示的併用を拒否する。旧項目だけの経路は乱数呼出し順も含めて変更しない。
- **根拠**: 新項目省略時の画像・スコア互換を守りつつ、大きさとコントラストを別々に調整できる。
- **代替案**: 旧項目を範囲へ自動変換すると旧画像の乱数列が変わり得るため採用しない。
- **実装規則 / 不変条件**: 保存済み分割画像と元画像を変更しない。`images_per_validation_image=1` かつ新範囲省略時は旧ファイル名・画像を維持する。
- **影響**: 設定型、擬似画像生成、評価契約。複数枚では推論時間と一時領域がほぼ枚数に比例する。

### 判断・候補: 同点の決定と上限到達の算定

- **状態**: 確定。
- **採用内容 / 候補**: `synthetic_auroc` の選択関数を共有し、正常完了試行だけを AUROC 降順、正常p99昇順、試行番号昇順で比較する。上限到達件数は同じ正常完了集合から数える。
- **根拠**: 現在の `study.best_trial` だけでは二次指標を反映できず、CLIと保存の試行が食い違う可能性がある。
- **代替案**: AUROCに微小なp99重みを加える方式は目的値を変え、厳密な同点規則を曖昧にするため採用しない。
- **実装規則 / 不変条件**: 比較は記録済みの有限値に限る。AUROC の元の値を変更しない。再開済み試行も数える。旧結果の未記録と新結果の0件を区別する。
- **影響**: `search`、`cli`、`artifacts`、共有結果型。`normal_percentile` の選択規則は維持する。

### 判断・候補: 雛形の条件

- **状態**: 確定。
- **採用内容 / 候補**: `part_XX.json` は `synthetic_auroc`、`size_px` 4〜128px、`intensity_range` 0.05〜0.5、`images_per_validation_image` 4を初期例とする。`intensity` は雛形から外す。
- **根拠**: 利用者は異常サイズが小さい場合も大きい場合もあると述べた。単一寸法・単一強度を避け、元の約130pxの異物より小さい側も試せる範囲とする。具体値は実画像の適合を確認した値ではない。
- **代替案**: 実異常の寸法が未測定のまま固定の最適値を宣言する案は採用しない。
- **実装規則 / 不変条件**: READMEに画像での確認、上限張り付き時の見直し、残り誤差と回転の実画像確認を明記する。既定の平行移動±1%・回転±1度はこの変更で変えない。
- **影響**: 新しい雛形を使う学習の目的と負荷。既存型番設定は変更しない。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 範囲逆転、非有限強度、0枚、旧・新強度の併用 | 設定読込 | 探索前に拒否、旧成果物保持 | 不正項目を表示 | CLIエラー | 設定修正 |
| 画像より大きい寸法・極小画像 | 画像生成 | 画像内へ制限し可視差分を保証 | 正常な擬似画像 | 必要なら条件を結果に記録 | 画像条件を再調整 |
| 生成失敗・非有限スコア・有効試行なし | 探索 | 失敗試行を採用しない、旧成果物保持 | 失敗理由 | 試行履歴・CLI | 入力修正後再実行 |
| 完了試行のp99欠落 | 選択 | 成果物更新せず終了 | 履歴不整合と `--restart` を表示 | CLIエラー | 対象グループ再学習 |
| 評価条件変更と既存履歴 | 探索作成 | 再開拒否、旧成果物保持 | 相違項目を表示 | CLIエラー | `train --restart` |
| 保存失敗・中断 | 成果物保存 | 旧一式へ復旧 | 失敗を表示 | 既存ジャーナル | 次回開始時に復旧 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 画素・枚数は真偽値を除く整数、強度は有限数だけ受け付ける | 不正値を探索前に拒否し旧成果物を保持 |
| 性能 | 擬似画像数は検証分割画像数×指定枚数。運用者が試行数と生成枚数を見て負荷を調整する | 雛形4枚時の実行時間・一時領域を対象環境で確認。上限値は未合意のため設けない |
| 運用 | 擬似画像・AUROC・上限警告を実異常の評価と区別する | READMEの手順と対象OSでの画像・JSON読戻しを確認 |
| 認証・外部連携 | ローカルCLIの既存境界を維持 | 今回は新しい権限・外部通信なし |

## 移行とロールバック

1. 既存型番設定はそのまま読み、擬似画像の旧経路を使う。新しい雛形は新規または明示的に更新した型番だけに適用する。
2. 既存型番で新しい検証条件・目的へ変更する場合は、旧成果物を必要に応じて退避し、対象グループで `train --restart`、続いて `test` を実行する。
3. 戻す場合は型番設定を旧条件に戻し、対応する旧探索履歴・checkpoint・結果を退避済みの一式から戻すか、旧条件で `train --restart` と `test` を実行する。異なる条件の履歴をそのまま再開しない。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-005 | REQ-005-S01 | integration | 正常・擬似スコアを返す複数試行 | 目的別の最良試行と状態 | `tests/test_training.py::test_req_005_s01_synthetic` | はい | テストダブルとOptuna | 実学習、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-002 | REQ-005 | REQ-005-S02 | integration | 擬似探索結果を表示 | 暫定指標と明示 | `tests/test_training.py::test_req_005_s02_synthetic` | はい | CLI表示 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-003 | REQ-005 | REQ-005-S03 | integration | 目的未指定の旧設定で探索 | 正常百分位最小 | `tests/test_training.py::test_req_005_s03` | はい | 設定・試行 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-004 | REQ-005 | REQ-005-S04 | unit / integration | AUROC同点、p99同点と差あり | p99、番号順に選択 | `tests/test_training.py::test_synthetic_auroc_tie_break` | はい | Optuna選択・保存 | 実学習、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-005 | REQ-007 | REQ-007-S01 | integration | 最良試行を保存 | 既存契約と件数を読戻す | `tests/test_training.py::test_best_trial_contains_synthetic_ceiling_count` | はい | JSON・checkpoint・閾値 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-006 | REQ-007 | REQ-007-S02 | integration | 重みキャッシュありで学習 | 再取得しない | `tests/test_training.py::test_training_reuses_pretrained_cache` | はい | 既存契約 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-007 | REQ-007 | REQ-007-S03 | integration | 保存時に例外注入 | 旧一式を復旧 | `tests/test_training.py::test_group_req_007_s03` | はい | 保存境界 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-008 | REQ-007 | REQ-007-S04 | integration | 不整合結果で検査 | 推論前に拒否 | `tests/test_training.py::test_group_req_007_s04` | はい | 結果読込 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-009 | REQ-007 | REQ-007-S05 | integration | 二つのグループで保存 | 閾値が独立 | `tests/test_training.py::test_group_req_007_s05` | はい | 成果物境界 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-010 | REQ-007 | REQ-007-S06 | integration | AUROC 1.0が複数 | 件数と警告 | `tests/test_training.py::test_synthetic_auroc_ceiling_warning` | はい | JSON・CLI警告 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-011 | REQ-007 | REQ-007-S07 | unit | 上限未到達と旧結果 | 0・nullの区別 | `tests/test_training.py::test_synthetic_ceiling_zero_and_legacy` | はい | 結果型・警告 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-012 | REQ-030 | REQ-030-S01 | unit | 同じ画像・seedで再生成 | 画素と選択が一致、原本不変 | `tests/test_synthetic_validation.py::test_req_030_s01` | はい | 4種類・同環境 | 対象OS、4.1 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-013 | REQ-030 | REQ-030-S02 | unit | 画素・強度の範囲と複数枚 | 枚数・可視差分・境界 | `tests/test_synthetic_validation.py::test_pixel_ranges_and_multiple_images` | はい | 生成処理 | 実画像、4.1 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-014 | REQ-030 | REQ-030-S03 | unit | 旧設定で生成 | 旧バイト列・同スコア | `tests/test_synthetic_validation.py::test_legacy_synthetic_bytes` | はい | 旧生成経路 | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-015 | REQ-030 | REQ-030-S04 | unit / integration | 不正な範囲・枚数 | 探索前拒否・旧成果物保持 | `tests/test_training.py::test_invalid_synthetic_ranges_preserve_artifacts` | はい | 設定とCLI | 対象OS、4.2 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| TC-016 | REQ-039 | REQ-039-S01 | integration | 雛形を設定として読込 | 新目的・範囲・枚数 | `tests/test_config.py::test_synthetic_template_defaults` | はい | 雛形・設定型 | 実画像での調整案内、4.3 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-005 | 4 | 4 | なし | 網羅 |
| REQ-007 | 7 | 7 | なし | 網羅 |
| REQ-030 | 4 | 4 | なし | 網羅 |
| REQ-039 | 1 | 1 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 4種類、大小の画素範囲、強度範囲、複数枚、同seed再現、原本不変 | TC-012〜TC-015、対象OSで画像比較 | Ubuntu 24.04 LTSの実画像・実学習、4.1 | 未検証 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| AC-002 | AUROCとp99同点、再開済み試行を含む選択 | TC-001・TC-004、結果JSON照合 | 対象OSの実学習、4.2 | 未検証 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| AC-003 | 1.0到達の複数・0件、旧結果null、警告 | TC-005・TC-010・TC-011、CLIとJSON読戻し | 対象OSのCLI、4.2 | 未検証 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| AC-004 | 旧設定の画像・目的・結果、契約相違による再開拒否・旧成果物保持 | TC-003・TC-014・TC-015、対象OSで旧設定を再実行 | 対象OSの旧設定での実学習、4.2 | 未検証 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |
| AC-005 | 雛形の新目的・条件と実測に基づく拡張強度の案内 | TC-016、README照合と実画像レビュー | 実画像での運用確認、4.3 | 未検証 | openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md |

## 未決事項

| 質問 | 回答期限 / 必要な工程 | 決定者 | 影響・未回答時の扱い |
| --- | --- | --- | --- |
| 各型番で実異常に合う画素・強度範囲と許容する学習時間は何か | 運用開始前 | 運用者・評価者 | 雛形は初期例として実装できるが、実異常での性能・運用開始を承認しない |
