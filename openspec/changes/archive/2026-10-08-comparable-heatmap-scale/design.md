## 背景・前提

`test` は型番設定を読み、checkpoint と暫定閾値を照合した後、分割画像の `pred_score` で判定する。`anomaly_map` は異常画像の可視化だけに使う。変更前の `_heatmap` はリサイズ後の画像ごとの最小値・最大値で 8-bit 色番号へ変換していた。結果は元画像単位の `InspectionResult` に保存し、`test --restart` で再生成できる。

型番設定は `src/app/common/config.py`、結果契約は `src/app/common/contracts.py`、描画は `src/app/model_evaluation/evaluation.py` が担当する。`config/part_XX.json` と `tests/fixtures/model_config.json` は設定例と試験の基礎データである。

## 目標・対象外

### 目標

- 一つの検査実行では型番別に指定された同一の表示範囲を全異常分割へ渡し、値から色番号への写像を画像の極値に依存させない。
- 表示範囲を設定と結果 JSON で検証可能にし、判定経路から分離する。
- 正常画像の保存内容と `pred_score >= threshold` の判定を維持する。

### 対象外

- 表示範囲の自動推定、checkpoint への格納、判定閾値の更新。
- 旧結果 JSON・画像の移行。利用者は本仕様適用後に再検査する。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-019 | データ契約と状態、インターフェースと失敗時の結果 | 型番設定の読込・検査開始 | 1.1, 1.2 | TC-001, TC-002 | 設定境界と CLI の自動試験 |
| REQ-010 | 業務フローと責務、技術判断 | 推論・判定・結果画像 | 2.1, 2.2 | TC-003, TC-004, TC-005, TC-006 | 固定画像・異常マップによる画素と判定の自動試験 |
| REQ-012 | データ契約と状態、インターフェースと失敗時の結果 | 元画像単位の JSON 契約 | 3.1, 3.2 | TC-007, TC-008, TC-009, TC-010 | 結果生成・読戻し・不正契約の自動試験 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 型番別設定 | 追加 | `heatmap_range` の下限・上限 | 検証済み範囲 | 設定読込 | `common/config.py` に確定。既存設定契約の担当 |
| 検査開始 | 変更 | 設定、checkpoint | 同じ表示範囲を全分割へ渡す | 型番別設定 | `model_evaluation/evaluation.py` に確定。既存の全分割ループの担当 |
| 可視化 | 変更 | 画像、異常マップ、表示範囲 | 異常画像の結果画像 | 推論結果 | `model_evaluation/evaluation.py` に確定。既存の `_heatmap` の担当 |
| 結果契約 | 追加 | 使用した表示範囲 | 元画像単位の JSON | 検査結果 | `common/contracts.py` に確定。既存の `InspectionResult` の担当 |

### 処理フロー

1. CLI が型番設定を読み込む。設定項目がない場合、`test` は推論・結果作成前に入力不備として終了する。範囲の型と順序が不正な場合も同様に拒否する。
2. 表示範囲を確定した後、既存の checkpoint・閾値照合を行う。各分割へ同じ表示範囲を渡す。
3. 各分割の推論結果の `pred_score` と有効な判定閾値を比較する。正常なら入力画像をそのまま保存する。異常なら同じ推論の `anomaly_map` をリサイズし、共通表示範囲へ切り詰めて色付けし、元画像に重ねて保存する。
4. 元画像単位の結果に使用した表示範囲を含める。位置合わせ失敗・分割エラーを含む結果にも、検査実行で使用した範囲を記録する。
5. 運用者が表示範囲を変更した場合、`test --restart` で既存結果を再生成する。このコマンドは旧結果を成果物照合より先に削除する既存動作を維持するため、旧結果が必要なら運用者が実行前に退避する。異なる範囲の結果を色だけで直接比較しない。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番別設定 | 追加 | `heatmap_range: {"min": number, "max": number}` (検査時必須) | 両値は有限、真偽値不可、`min < max`。`0`〜`1` 制約なし | 運用者 | 旧設定は検査前に追記。学習・画像準備の読込は妨げない |
| 結果 JSON | 追加 | `heatmap_range: {"min": number, "max": number}` (必須) | 型番別設定で検査時に確定した値と一致 | 検査処理 | 旧結果の移行なし。新契約での読戻しは旧 JSON を拒否 |
| 異常スコア・閾値 | 変更なし | 既存の `score`、`threshold` | `pred_score >= threshold` | 既存処理 | 表示範囲との連動なし |

設定モデルでは `heatmap_range` を省略可能にして既存の学習・画像準備経路を維持し、`test` 開始時に必須性を検証する。範囲オブジェクト自体は型・有限性・順序を設定読込時に検証する。結果モデルでは常に必須とする。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `test --model` | 運用者 → CLI | 型番設定、checkpoint、試験画像 | 結果画像と表示範囲付き JSON | 範囲なし・不正 → 終了コード 2、項目と理由を標準エラーへ出し推論前に終了。`--restart` では旧結果が削除済みの場合がある | 設定修正後に再実行。旧結果が必要なら `--restart` 前に退避 |
| 結果 JSON 読戻し | 評価者・後続処理 → 結果契約 | 保存 JSON | 範囲を含む検査結果 | 範囲欠落・不正 → 検証エラー | 正しい結果を再生成 |
| 異常画像保存 | 検査処理 → 画像出力 | 画像、異常マップ、範囲 | 共通尺度の画像 | 画像処理失敗 → 既存の分割 `error` と元画像判定規則を使用 | 入力確認後に再検査 |

## 技術判断

### 判断 1: 表示範囲の保持場所と必須性

- **状態**: 確定
- **採用内容**: 型番別設定に `heatmap_range.min/max` を置く。設定読込では省略を許し、`test` 開始前に必須とする。結果 JSON には使用範囲を必須で保存する。
- **根拠**: 運用者が指定でき、同一検査内の分割に同じ値を渡せる。学習と画像準備は表示範囲を使用しない。
- **代替案**: checkpoint に格納すると範囲変更だけの再検査に再学習が必要となる。画像ごとの自動推定は比較可能性を満たさない。
- **実装規則 / 不変条件**: 判定閾値と混同せず、値の更新で checkpoint や暫定閾値を書き換えない。
- **影響**: 型番別設定の検査入力と結果 JSON の契約が変わる。

### 判断 2: 色番号への変換

- **状態**: 確定
- **採用内容**: リサイズ後の `anomaly_map` を `min/max` で線形に 0〜255 の色番号へ写し、範囲外は切り詰める。既存の JET 色表と画像への重ね合わせ比率を維持する。
- **根拠**: 固定範囲内で同じ値が同じヒートマップ色になり、表示だけを変えられる。
- **代替案**: 画像ごとの最小・最大値は目的に反する。判定閾値を色の中心に使う案は `pred_score` と `anomaly_map` の尺度を混同する。
- **実装規則 / 不変条件**: 判定を先に確定し、異常画像だけ描画する。同じ異常マップ値に割り当てるヒートマップ層の色を揃える。元画像と混合した最終画素の色は元画像色に依存し、一致を要求しない。
- **影響**: 異常結果画像の見た目が変わる。スコア、閾値、判定は変えない。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 範囲なし、片側欠落、不正型・非有限・逆順 | 設定・検査開始 | 推論・新結果作成を開始しない。`--restart` の旧結果削除は既存動作 | 終了コード 2 と項目・理由 | 既存 CLI 実行記録 | 設定修正後再実行。旧結果が必要なら事前退避 |
| 範囲外の異常マップ値 | 可視化 | 端の色に固定 | 結果画像を保存 | 結果 JSON に使用範囲 | 運用者が必要に応じ範囲を見直し再検査 |
| 異常マップの画像処理失敗 | 分割検査 | 当該分割を `error` として集約 | 分割エラーと元画像判定 | 既存エラー記録 | 入力・モデル確認後再検査 |
| 古い結果 JSON の読戻し | 結果契約 | 新契約として受理しない | 必須範囲の欠落を示す | 読戻し側エラー | 再検査で新結果を生成 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 非有限値と真偽値を排除し、範囲を検査前に確定 | 不正設定の CLI エラーと結果未保存 |
| 性能 | 既存のリサイズ・色表・重ね合わせを利用し、画像ごとの極値計算を除く | 追加のモデル推論なし。既存の処理時間記録で確認 |
| 運用 | モデル変更時に範囲を確認し、表示変更後は `test --restart` で再生成。同じ学習済みモデルかどうかは運用で確認し、結果 JSON の checkpoint パスだけで同一性を判定しない | 比較対象のモデル確認と結果 JSON の表示範囲を照合 |

認証・認可や外部通知は既存のローカル CLI に存在せず、この変更の対象外である。

## 移行とロールバック

1. 運用者は検査前に各型番設定へ `heatmap_range` を追加する。下限・上限の具体値は対象モデルの異常マップ値を評価して決める。本 change はモデル固有の数値を推測しない。
2. 旧結果は移行しない。必要な画像は新仕様で再検査する。`test --restart` で旧結果が必要なら実行前に退避し、失敗時の旧結果保持は要求しない。
3. ロールバックする場合は旧コード・旧型番設定を組にして戻し、必要なら旧方式で再検査する。新しい結果 JSON を旧コードで読み戻せるとはみなさない。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-019 | REQ-019-S01 | unit | 0〜1 外の有限値の範囲を設定し読込 | 値を保持し判定設定は不変 | `tests/test_config.py::test_heatmap_range_accepts_finite_bounds_outside_score_range` | はい | 設定モデル・ローカル環境 | CLI 確認 (4.5) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-002 | REQ-019 | REQ-019-S02 | integration | 範囲なし・片側欠落・不正型・非有限・逆順で `test` | 項目と理由、終了コード 2、推論と新結果なし | `tests/test_evaluation.py::test_evaluation_rejects_invalid_heatmap_range_before_prediction` | はい | 設定・検査入口のテストダブル | CLI 確認 (4.5) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-003 | REQ-010 | REQ-010-S01 | integration | 閾値未満の分割を検査 | 正常判定、元画像を保存 | `tests/test_evaluation.py::test_evaluation_records_normal_split` | はい | 固定画像・予測ダブル | 対象 OS 確認 (4.3) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-004 | REQ-010 | REQ-010-S02 | integration | 閾値以上の分割を検査 | 異常判定、指定範囲で色付けした画像を保存 | `tests/test_evaluation.py::test_evaluation_visualizes_anomalous_split` | はい | 固定画像・予測ダブル | 対象 OS 確認 (4.2・4.3) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-005 | REQ-010 | REQ-010-S03 | unit | 既存前処理付きモデルで推論 | 同一決定的前処理 | `tests/test_evaluation.py::test_predictor_uses_model_preprocessor` | はい | モデル前処理の既存試験 | 対象 OS 確認 (4.3) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-006 | REQ-010 | REQ-010-S04 | unit | 異なる極値の 2 マップへ同じ範囲を適用 | ヒートマップ層の同値同色、端色固定、判定不変。重ね合わせ後の画素一致は要求しない | `tests/test_evaluation.py::test_heatmap_uses_shared_range_across_images` | はい | 色番号と重ね合わせの固定画像試験 | 対象 OS 確認 (4.2・4.3) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-007 | REQ-012 | REQ-012-S01 | integration | 正常・異常・未判定の結果を生成 | 使用範囲が各 JSON に保存 | `tests/test_evaluation.py::test_evaluation_records_heatmap_range_in_results` | はい | 結果生成・読戻し | 対象 OS 確認 (4.4) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-008 | REQ-012 | REQ-012-S02 | unit | 範囲欠落・不正の JSON を読戻し | 契約違反として拒否 | `tests/test_results.py::test_result_rejects_invalid_heatmap_range` | はい | Pydantic 結果契約 | なし | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-009 | REQ-012 | REQ-012-S03 | integration | 同 stem・異拡張子の結果を作成 | 上書きなし | `tests/test_evaluation.py::test_evaluation_keeps_same_stem_different_extensions` | はい | 既存結果保存試験 | なし | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| TC-010 | REQ-012 | REQ-012-S04 | integration | 型番不一致、危険なパス、重複・参照不整合を含む試験 manifest で検査する | 推論前に拒否し、結果領域と領域外ファイルを変更しない | `tests/test_evaluation.py::test_evaluation_rejects_invalid_manifest_before_prediction` | はい | 検査入口と manifest 契約をテストダブルで確認 | 対象 OS 確認 (4.5) | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-019 | 2 | 2 | なし | 網羅 |
| REQ-010 | 4 | 4 | なし | 網羅 |
| REQ-012 | 4 | 4 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 運用で同一性を確認したモデル・同じ表示範囲の異常画像、対象 OS。比較対象はヒートマップ層 | TC-004, TC-006 と対象 OS での結果画像確認 | Ubuntu 24.04 LTS・Windows 11 の実モデル確認 (4.2) | 未検証 | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| AC-002 | 正常・異常分割、スコアと判定の独立性、対象 OS | TC-001, TC-003, TC-004, TC-006 と対象 OS 確認 | Ubuntu 24.04 LTS・Windows 11 の実画像確認 (4.3) | 未検証 | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| AC-003 | 再検査前後の結果 JSON | TC-007, TC-008 と `test --restart` の確認 | Ubuntu 24.04 LTS・Windows 11 の再検査確認 (4.4) | 未検証 | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |
| AC-004 | 未指定・不正設定の CLI と結果領域 | TC-002 と CLI 実行 | Ubuntu 24.04 LTS・Windows 11 の CLI 確認 (4.5) | 未検証 | `openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` |

## 未決事項

| 質問 | 回答期限 / 必要な工程 | 決定者 | 影響・未回答時の扱い |
| --- | --- | --- | --- |
| 実際の型番と学習済みモデルに設定する下限・上限の数値 | 当該型番の運用開始前 | 運用者・評価者 | 実装・自動試験は固定の試験値で可能。実データの色解釈と受け入れは値の確定まで保留 |
