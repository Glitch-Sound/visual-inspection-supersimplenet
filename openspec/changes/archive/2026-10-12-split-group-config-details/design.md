## 背景・前提

型番設定は `src/app/common/config.py` で検証され、各能力は結合済みの `GroupConfig` を利用する。<br />
学習時の暫定閾値は同ファイルの `write_threshold` が対象グループへ書き戻す。<br />
配布雛形と試験fixtureは現在 `groups` に全項目を置く。

## 目標・対象外

### 目標

- 外部JSONの `groups` と `group_detail` をIDで一対一に対応付け、既存の内部 `GroupConfig` に変換する。
- 対象IDの `group_detail` だけへ暫定閾値を書き戻す。

### 対象外

- 学習・検査の計算、CLI、成果物の形式変更。
- 旧形式の自動変換。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-021 | データ契約と状態、失敗時の結果 | 設定読込 | 1.1, 1.2, 2.1 | TC-001〜TC-005 | pytestで有効設定と拒否を確認 |
| REQ-029 | データ契約と状態、処理フロー | 設定書戻し | 1.3, 2.1 | TC-006, TC-007 | pytestで対象だけの更新と失敗時の不変を確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 設定読込 | 変更 | 新形式JSON | 結合済み `GroupConfig` | 共通設定 | `common/config.py` で確定 |
| 学習設定書戻し | 変更 | 対象IDと暫定閾値 | `group_detail` の対象値更新 | 設定読込 | `common/config.py` で確定 |
| 設定雛形と案内 | 変更 | 新形式 | 複製・編集可能な例 | なし | `config/part_XX.json` と README |

### 処理フロー

1. 読込時に `groups` の各要素と `group_detail` のキーを照合する。
2. ID、範囲、検査条件、詳細設定の型と値を検証し、同じIDの内容を既存の内部 `GroupConfig` に組み立てる。
3. 不一致、混在、旧形式なら成果物の更新前に入力不備として拒否する。
4. 学習完了時は元のJSONにある対象IDの `group_detail` の暫定閾値を更新し、他の順序と値を保持して原子的に置き換える。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| `groups` | 変更 | 非空配列、各要素に `id`, `range_ids`、任意の `inspection_threshold`, `heatmap_range` | IDは一意の非負整数。検査時は有効な表示範囲が必要 | 運用者 | 旧詳細項目を移動 |
| `group_detail` | 追加 | ID文字列から `optuna_settings`, `score`, `augmentation` への対応表 | キーは0埋めなしの10進整数文字列、集合は `groups` のIDと一致 | 運用者、学習時は閾値だけ更新 | 旧設定は手動で分割 |
| 内部 `GroupConfig` | 変更なし | 全設定の結合済みモデル | 既存の値検証と処理側インターフェースを維持 | 設定読込 | 成果物には影響しない |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 5 CLI | 運用者 → 設定読込 | 新形式の型番設定 | 対応するグループを使用 | ID不一致・混在・旧形式 → 入力不備、成果物不変 | 設定修正後に再実行 |
| 学習の閾値書戻し | 学習 → 設定ファイル | 対象IDと数値 | 対象詳細だけ更新 | 詳細欠落・不正 → 更新しない | 設定修正後に再実行 |

## 技術判断

### 判断: 外部形式だけを分ける

- **状態**: 確定。
- **採用内容**: 読込境界で `groups` と `group_detail` を結合し、内部の `GroupConfig` は維持する。
- **根拠**: 画像準備、学習、検査が同じグループ設定を使うため、外部形式の変更を境界に閉じ込められる。
- **代替案**: 各能力に別々の設定参照を渡す案は変更範囲が広がる。
- **実装規則 / 不変条件**: 両領域に同じ項目を重複させず、IDキーは `str(id)` と完全一致する。`"00"` や負数は拒否する。
- **影響**: 設定読込、書戻し、雛形、fixture、設定を変更する試験。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 詳細の欠落・余分 | 設定読込 | 書込みなし | IDと不一致理由 | CLIエラー | 対応を修正 |
| 旧形式・項目混在 | 設定読込 | 書込みなし | 混在項目を示す | CLIエラー | 詳細項目を移動 |
| 書戻し時に設定変更 | 書戻し | 置換前に再検証 | 不正設定を拒否 | 学習エラー | 設定修正後に再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 既存の厳格な数値・項目検証を維持し、詳細キーの型・書式・集合を追加検証 | 異常系pytest |
| 運用 | 旧設定を手動で新形式へ移し、checkで検証する | 型番設定とCLI結果 |

## 移行とロールバック

1. 既存の型番設定を退避し、各 `groups` から3つの詳細項目を同じIDの `group_detail` へ移す。
2. `uv run --locked check --model <型番>` で設定を確認し、その後に学習・検査を実行する。準備指紋と学習成果物の契約は変えない。
3. ロールバック時は変更前のコードと退避した旧形式の設定を組で戻す。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-021 | REQ-021-S01 | unit | 2グループの新形式を読込 | 対応する詳細を使う | `tests/test_config.py::test_group_req_021_s01` | はい | 設定契約 | 対象OSの5 CLI (3.3) | `openspec/changes/split-group-config-details/evidence/automated.md` |
| TC-002 | REQ-021 | REQ-021-S02 | unit | 不正ID・範囲・値 | 入力不備 | `tests/test_config.py::test_group_req_021_s02` | はい | 設定契約 | 対象OSの5 CLI (3.3) | `openspec/changes/split-group-config-details/evidence/automated.md` |
| TC-003 | REQ-021 | REQ-021-S03 | unit | groups欠落 | 入力不備 | `tests/test_config.py::test_group_req_021_s03` | はい | 設定契約 | 対象OSの5 CLI (3.3) | `openspec/changes/split-group-config-details/evidence/automated.md` |
| TC-004 | REQ-021 | REQ-021-S04 | unit | 詳細キー欠落・余分・非標準 | ID不一致を拒否 | `tests/test_config.py::test_group_detail_rejects_mismatched_ids` | はい | 設定契約 | 対象OSの5 CLI (3.3) | `openspec/changes/split-group-config-details/evidence/automated.md` |
| TC-005 | REQ-021 | REQ-021-S05 | unit | 両領域に項目混在 | 入力不備 | `tests/test_config.py::test_group_detail_rejects_mixed_fields` | はい | 設定契約 | 対象OSの5 CLI (3.3) | `openspec/changes/split-group-config-details/evidence/automated.md` |
| TC-006 | REQ-029 | REQ-029-S01 | unit / integration | 2グループの閾値書戻し | 対象のみ更新 | `tests/test_config.py::test_training_threshold_updates_only_one_group` | はい | 設定書戻し | 実モデル学習 (3.5) | `openspec/changes/split-group-config-details/evidence/automated.md` |
| TC-007 | REQ-029 | REQ-029-S02 | unit | 詳細欠落の設定で学習開始 | 既存設定を更新しない | `tests/test_config.py::test_invalid_group_detail_keeps_config` | はい | 読込前拒否 | 実モデル学習 (3.5) | `openspec/changes/split-group-config-details/evidence/automated.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-021 | 5 | 5 | なし | 網羅 |
| REQ-029 | 2 | 2 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | Ubuntu 24.04 LTS・Windows 11で複数グループの新形式 | 5 CLIを全件・単独で実行 | 対象OSの実行 (3.3) | 未検証 | `openspec/changes/split-group-config-details/evidence/automated.md` |
| AC-002 | 両OSで不正設定と既存成果物 | 設定異常を与えて拒否・不変を照合 | 対象OSの実行 (3.4) | 未検証 | `openspec/changes/split-group-config-details/evidence/automated.md` |
| AC-003 | 両OSで対象グループの実学習 | 学習後の型番設定を比較 | 対象OSの実行 (3.5) | 未検証 | `openspec/changes/split-group-config-details/evidence/automated.md` |
