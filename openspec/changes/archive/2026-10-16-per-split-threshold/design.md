## 背景・前提

現行の `SourceScore` は元画像名、分割画像名、スコアを持ち、`BestTrialResult.score_by_source` に学習対象外スコアが残る。<br />
`model_training/artifacts.py` は全スコアからグループ閾値を算出し、設定・最良試行・checkpointを一式更新する。<br />
`model_evaluation/evaluation.py` はグループ閾値と手動上書きを選び、全分割に適用する。<br />
設定と保存データの共有契約は `src/app/common/`、学習と検査は各能力のパッケージに置く。

## 目標・対象外

### 目標

- 分割ID別の学習対象外スコアから、設定件数以上の分割について暫定閾値を再現可能に算出する。
- 不足分割は学習時のグループ暫定閾値を使い、警告と由来を保存する。
- グループ単位の既定動作と元画像の集約を維持し、分割ごとの閾値と由来を結果JSONから読み戻せるようにする。

### 対象外

- 交差検証の分割方法、モデル学習、スコア尺度、ヒートマップ表示の変更。
- 実画像の検出性能目標の設定。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-036 | 処理フロー、データ契約と状態 | 学習結果の算出・保存 | 2.1, 2.2 | TC-001〜TC-003 | 算出値、代替記録、従来値をpytestで照合 |
| REQ-037 | データ契約と状態、インターフェースと失敗時の結果 | 設定・成果物整合 | 1.1, 2.3 | TC-004〜TC-006 | 不正入力と成果物不一致をpytestで拒否確認 |
| REQ-038 | 処理フロー、データ契約と状態 | 検査結果・集約 | 3.2 | TC-007〜TC-008 | 結果JSON、未判定をpytestで確認 |
| REQ-018 | 処理フロー、インターフェースと失敗時の結果 | 閾値選択・検査 | 3.1, 3.2 | TC-009〜TC-015 | 従来互換、上書き、境界、拒否をpytestで確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 設定と保存契約 | 変更 | 閾値単位、最少件数、分割別上書き | 検証済み設定と結果型 | 型番JSON | `common/config.py`、`common/contracts.py` に確定。既存共有契約の責務 |
| 暫定閾値算出・一式保存 | 変更 | 最良試行、学習対象外スコア | グループ・分割別値、警告、成果物 | 共通契約・既存トランザクション | `model_training/artifacts.py` に確定。既存算出・保存経路 |
| 学習再開契約 | 変更 | 閾値単位と最少件数 | 変更時の再開拒否 | 探索履歴 | `model_training/search.py` に確定。既存契約検査 |
| 検査時の閾値選択 | 変更 | 設定、最良試行、checkpoint | 分割別の適用値・由来 | 共通契約 | `model_evaluation/evaluation.py` に確定。既存の検査経路 |
| 検査結果の保存 | 変更 | 分割別判定 | 閾値・由来付きJSON | 共通契約 | `model_evaluation/evaluation.py` と既存結果世代経路に確定 |

### 処理フロー

1. 運用者が設定を読み込む。<br />
共通設定契約は単位、最少件数、対象分割ID、手動上書きを検証し、不正なら学習・検査開始前に拒否する。
2. 学習は従来どおりグループ暫定閾値を算出する。<br />
分割ID単位なら学習対象外スコアの分割画像名を準備manifestの命名規則と対象IDで照合し、IDごとに集める。<br />
十分な件数は同じパーセンタイルとマージンで算出し、不足時はグループ値を記録して警告する。
3. 算出結果を設定、最良試行、checkpointメタデータへ既存の一式更新で保存する。<br />
失敗時は旧一式を保持する。<br />
単位または最少件数を変えた探索履歴の再開は拒否し、`train --restart` を案内する。
4. 検査前に設定・最良試行・checkpointの単位、最少件数、グループ値、分割別値・由来・対象IDの一致を確認する。<br />
不一致なら推論と結果世代の切替を行わない。
5. 検査は分割IDごとに、手動上書きがあればそれを、なければ学習由来の算出値またはグループ代替値を選ぶ。<br />
グループ単位では既存の選択を使う。<br />
推論失敗時も選択値を分割結果に記録し、集約規則は変更しない。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| `group_detail.<id>.optuna_settings.threshold` | 追加 | `unit: group|split`、`min_score_count: int|null`、`split_values: map` | `unit` 省略時 `group`。`split` の時だけ件数必須、1以上。`split_values` は学習が書く | 設定読込・学習 | 旧設定は `group` として読める |
| `groups[].inspection_threshold_by_split` | 追加 | 分割IDの10進文字列から数値またはnullへの辞書 | 対象IDのみ、数値は有限な0〜1。`split` 単位でのみ有効 | 運用者 | 省略時は空。グループの手動値と独立 |
| 分割別学習値 | 追加 | 各IDに `value: float`、`source: calculated|group_fallback`、`score_count: int` | 対象全IDを網羅。代替値はグループ暫定閾値と等しい | 学習 | 最良試行、checkpointにも同じ地図を保存 |
| `SplitResult` | 追加 | `threshold: float`、`threshold_source: str` | `split_calculated`、`group_fallback`、`manual_override`、`group_calculated`、`group_manual_override` | 検査 | 旧JSON読込は任意フィールドとして許容し、新結果には必ず書く |
| `InspectionResult.threshold` | 維持 | グループの適用閾値 | 分割ID単位では学習由来のグループ暫定閾値を保持 | 検査 | 既存読戻し契約を維持。各分割の実適用値は `splits` で読む |

分割IDは `range_ids` の整数に対応し、JSONキーは通常の10進文字列とする。<br />
`score_by_source` の分割画像名からIDを取り出す際は既存準備manifestの `<元画像stem>_<2桁以上のID><拡張子>` に完全一致することを確かめる。<br />
分割別の手動上書きは学習成果物に混ぜない。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train` | CLI → 学習 | 型番・グループ設定と準備結果 | 閾値と警告を含む成果物 | 不正設定・スコア不正 → 理由表示、旧成果物維持 | 修正後 `--restart`。既存ロックと一式更新を使用 |
| `test` | CLI → 検査 | 型番・グループ設定、学習成果物 | 分割別の値・由来を含むJSON | 不整合 → 推論前に拒否、現行結果維持 | 修正・再学習後に再実行。既存結果世代方式を使用 |
| 結果読戻し | 評価者 → JSON | `current.json` の参照 | 使用値・由来と判定 | 旧JSONで新フィールドなし → 旧契約として読める | 書換えなし |

## 技術判断

### 判断・候補: 分割別算出値の保存先

- **状態**: 確定
- **採用内容 / 候補**: グループ暫定値を残し、設定・最良試行・checkpointに同じ分割別値、由来、件数を保存する。
- **根拠**: 既存の3成果物整合検査と一式復旧を拡張できる。
- **代替案**: 最良試行のみ保存する案は設定とcheckpointの整合確認が弱くなるため採用しない。
- **実装規則 / 不変条件**: 3成果物の単位・件数・ID集合・値・由来を一致させる。<br />
代替値はグループ暫定値と一致させる。
- **影響**: 分割ID単位への切替には対象グループの再学習が必要。

### 判断・候補: 手動上書きの優先順位

- **状態**: 確定
- **採用内容 / 候補**: 分割ID単位では分割ID別の手動値を最優先し、なければ保存済み分割別値を使う。<br />
グループの手動値はグループ単位にだけ使う。
- **根拠**: 学習時のグループ代替値を後から変更せず、由来を一意にできる。
- **代替案**: グループ手動値を代替に重ねる案は学習時の代替記録と食い違うため採用しない。
- **実装規則 / 不変条件**: 手動値は暫定値を変更しない。<br />
スコアと使用閾値が等しければ異常。
- **影響**: 分割ID単位では既存 `groups[].inspection_threshold` は判定に影響しない。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 件数が最少値と等しい | 学習 | 分割別に算出 | 算出値を取得 | 件数を保存 | 不要 |
| 件数不足または0件 | 学習 | グループ値を保存 | 分割ID・件数・理由の警告 | CLI記録と最良試行 | データ追加後に再学習 |
| 非有限・欠落スコア | 学習 | 完成済み一式を維持 | 失敗理由を表示 | エラー記録 | 入力修正後に再学習 |
| 設定・成果物の不一致 | 検査前照合 | 旧結果を維持 | 不一致の対象を表示 | エラー記録 | `train --restart` 後に検査 |
| 分割推論失敗 | 検査 | errorまたは未判定として結果に保存 | 閾値・由来とエラーを確認 | 既存の警告・エラー記録 | 原因修正後に再検査 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 分割ID、数値、件数、単位を厳格に検証する | 不正入力は学習・推論前に拒否 |
| 性能 | 保存済み学習対象外スコアをID別に一度分類する | 新たな交差検証実行を追加しない。処理時間の本番目標は対象外 |
| 運用 | 分割ID単位への変更時に `train --restart`、続いて `test` を行う | 警告、3成果物、結果JSONを確認 |
| 認証・認可 | 対象外 | ローカルCLIであり既存の権限境界を変更しない |

## 移行とロールバック

1. 既存型番は単位省略でグループとして扱い、変更しない場合は再学習不要とする。
2. 分割ID単位へ切り替える型番は設定に単位と最少件数を追加し、対象グループを `train --restart` で再学習して `test` の結果を再生成する。
3. 旧動作へ戻す場合は設定をグループ単位へ戻し、分割ID単位で保存された `min_score_count`、`split_values`、分割ID別の手動上書きを設定から削除する。<br />
`train --restart` でグループ単位の成果物を作り直し、`test` で結果を再生成する。

## 試験設計

全自動試験はテストダブルまたは小規模フィクスチャで契約を確認する。<br />
実ライブラリ・対象OS・実画像での検証はタスク5.2に残し、証跡は実施後に記録する。

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-036 | REQ-036-S01 | unit | 2分割、十分なスコアで学習 | ID別のパーセンタイルとグループ値 | `tests/test_training.py::test_split_threshold_calculation` | はい | 算出契約 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-002 | REQ-036 | REQ-036-S02 | unit | 0件・境界未満で学習 | 代替値・件数・警告 | `tests/test_training.py::test_split_threshold_fallback_warning` | はい | 代替契約 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-003 | REQ-036 | REQ-036-S03 | integration | 単位省略で学習 | 既存グループ値と一致 | `tests/test_training.py::test_group_threshold_default_compatibility` | はい | 従来互換 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-004 | REQ-037 | REQ-037-S01 | unit | 不正単位・最少件数で開始 | 拒否・旧成果物維持 | `tests/test_config.py::test_split_threshold_settings_rejected` | はい | 設定検証 | なし | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-005 | REQ-037 | REQ-037-S02 | unit | 分割単位と従来方式で開始 | 拒否理由 | `tests/test_config.py::test_split_threshold_requires_oof` | はい | 設定検証 | なし | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-006 | REQ-037 | REQ-037-S03 | integration | 3成果物のID・値を改変して検査 | 推論前拒否、旧結果維持 | `tests/test_evaluation.py::test_split_threshold_artifact_mismatch` | はい | 成果物整合 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-007 | REQ-038 | REQ-038-S01 | integration | 3由来の分割を検査しJSON読戻し | 各値・由来、異常優先集約 | `tests/test_evaluation.py::test_split_threshold_result_provenance` | はい | 結果契約 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-008 | REQ-038 | REQ-038-S02 | integration | 一分割で推論失敗 | error、値・由来、未判定 | `tests/test_evaluation.py::test_split_threshold_prediction_error` | はい | 失敗時契約 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-009 | REQ-018 | REQ-018-S01 | integration | グループ単位・上書き省略で検査 | 既存値・判定 | `tests/test_evaluation.py::test_group_threshold_default_compatibility` | はい | 従来互換 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-010 | REQ-018 | REQ-018-S02 | unit | グループ上書きnullで検査 | 暫定値 | `tests/test_evaluation.py::test_group_null_threshold_compatibility` | はい | 値選択 | なし | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-011 | REQ-018 | REQ-018-S03 | unit | グループ上書きありで検査 | 上書き値、暫定値不変 | `tests/test_evaluation.py::test_group_manual_threshold_compatibility` | はい | 値選択 | なし | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-012 | REQ-018 | REQ-018-S04 | unit | 0・1と同値スコアで検査 | anomaly | `tests/test_evaluation.py::test_split_threshold_boundaries` | はい | 境界値 | なし | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-013 | REQ-018 | REQ-018-S05 | unit | 範囲外・非数・未知IDで検査 | 推論前拒否、旧結果維持 | `tests/test_evaluation.py::test_split_manual_threshold_rejected` | はい | 設定拒否 | なし | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-014 | REQ-018 | REQ-018-S07 | integration | 一分割を手動上書きして検査 | 対象のみ変更、暫定値不変 | `tests/test_evaluation.py::test_split_manual_threshold_override` | はい | 優先順位 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| TC-015 | REQ-018 | REQ-018-S06 | integration | 手動値ありで暫定値を改変して検査 | 不一致を推論前に拒否 | `tests/test_evaluation.py::test_manual_override_does_not_hide_mismatch` | はい | 成果物整合 | 実画像、5.2 | openspec/changes/per-split-threshold/evidence/acceptance.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-036 | 3 | 3 | なし | 網羅 |
| REQ-037 | 3 | 3 | なし | 網羅 |
| REQ-038 | 2 | 2 | なし | 網羅 |
| REQ-018 | 7 | 7 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | グループ単位の学習・検査、既存設定 | TC-003、TC-009〜TC-011と対象OS実行 | 対象OSの実画像、5.2 | 未検証 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| AC-002 | 分割別算出、件数不足、警告 | TC-001、TC-002と実スコア再計算 | 対象OSの実画像・スコア再計算、5.2 | 未検証 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| AC-003 | 分割別手動上書き、暫定値不変 | TC-012〜TC-014と対象OS実行 | 対象OSの実画像、5.2 | 未検証 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| AC-004 | 結果JSON、異常優先集約、未判定 | TC-007、TC-008と結果読戻し | 対象OSの結果JSON読戻し、5.2 | 未検証 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| AC-005 | 不正設定、成果物不整合、旧結果保持 | TC-004〜TC-006、TC-013 | 対象環境での拒否と旧結果読戻し、5.3 | 未検証 | openspec/changes/per-split-threshold/evidence/acceptance.md |
| AC-006 | Ubuntu 24.04 LTS・Windows 11の実画像と利用可能なCPU/GPU | 実機で学習・検査し保存値とJSONを照合 | 対象OS実機、5.2 | 未検証 | openspec/changes/per-split-threshold/evidence/acceptance.md |
