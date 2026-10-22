## 背景・前提

`ModelConfig.combine_group_details` は `group_detail` を `GroupConfig` に統合し、未知の詳細項目を拒否する。<br />
学習の `AnomalibTrialRunner` は `create_supersimplenet` でモデルを作る。検査の `CheckpointPredictor` も同じ生成関数を呼び、eval モードで推論する。<br />
Anomalib 2.6.2 の `AnomalyGenerator` は特徴を複製し、Perlin mask を生成して Gaussian ノイズを重ねる。現行の `generate_perlin` は mask ごとに閾値、Perlin scale、50% の適用判定を扱い、`forward` は noise、mask、label と特徴を更新する。<br />
`generate_perlin_noise` は `scale=(2^n_x, 2^n_y)` を受け取る。現行コードは `execution.seed` を最良試行記録に保存する一方、torch へ明示的に設定していないため、学習試行開始時に既存の `execution.seed` を torch に適用する設計とする。

## 目標・対象外

### 目標

- グループ詳細の任意設定を厳密に検証し、欠落した範囲に推奨値を適用する。
- mask ごとに noise、閾値、縦横 scale を独立に選び、Anomalib 2.6.2 の生成手順を保つ。
- 学習時だけ設定を適用し、既存の探索パラメータと検査結果契約を維持する。

### 対象外

- 擬似異常範囲の Optuna 探索、検査時の生成、旧成果物の読戻し・移行。
- 実異常画像による検出性能の数値目標。本変更の初期評価と別途決定する。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-032 | データ契約と状態、処理フロー | 設定 → 学習モデル | 1.1, 2.2 | TC-001, TC-002 | 設定読込とグループ別モデルの自動試験 |
| REQ-033 | 技術判断、処理フロー | 学習モデル → 擬似異常生成 | 2.1, 2.2 | TC-003, TC-004 | 実生成器と固定乱数による自動試験 |
| REQ-034 | データ契約と状態、境界条件と失敗モード | 設定 → CLI | 1.1, 3.1 | TC-005, TC-006 | 入力境界と既存成果物保全の自動試験 |
| REQ-035 | インターフェースと失敗時の結果、移行とロールバック | 学習探索 / 検査 | 2.2, 3.2, 4.1 | TC-007, TC-008 | 探索履歴と推論結果の自動試験、対象 OS 確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 型番設定の検証 | 変更 | `group_detail[*].synthetic_anomaly` | 検証済み `GroupConfig` または入力不備 | 既存 CLI | `src/app/common/config.py` に確定。共有設定契約であるため |
| 擬似異常の生成 | 追加 | 検証済み範囲、特徴、mask、label、torch 乱数 | 学習用の特徴・mask・label | Anomalib 2.6.2 | `src/app/common/model_adapter.py` に確定。既存の共有モデル生成境界に含め、`common/` から個別能力への依存を作らないため |
| モデルへの適用 | 変更 | 学習モデル、グループ設定 | 生成器を持つ学習モデル | モデル生成関数 | `src/app/common/model_adapter.py` と `src/app/model_training/trainer.py` に確定。既存の生成境界を使用するため |
| 検査 | 維持 | checkpoint、分割画像 | 既存形式の結果 | 既存評価能力 | 生成器を実行しないことを `tests/test_model_adapter.py` と `tests/test_evaluation.py` で確認 |

### 処理フロー

1. 運用者が設定を読み込む CLI を実行すると、共通設定が各グループ詳細を統合し、範囲の型、有限性、順序、境界を検証する。入力不備なら既存の終了コード2で、成果物を更新せず終了する。
2. 学習試行開始時、既存の `execution.seed` を torch の乱数に設定し、対象グループの検証済み設定をモデル生成境界へ渡す。探索の候補集合には加えない。
3. モデル作成後、内部の `anomaly_generator` を案件用の `AnomalyGenerator` 派生クラスに差し替える。mask ごとに4つの値 (標準偏差、閾値、縦指数、横指数) を選び、標準正規ノイズに標準偏差を掛ける。Perlin 生成には `scale=(2^n_x, 2^n_y)` を渡す。選ばれた scale が特徴マップと同等以上の軸では、格子点だけを評価して一定値になることを避けるため、生成領域を scale の2倍以上の2の累乗まで広げ、既存の補間で特徴マップへ合わせる。
4. Perlin の二値化、50% の無異常化、既存 mask との非重複、label 更新、特徴の複製と合成は Anomalib 2.6.2 の手順を維持する。学習失敗時の旧成果物保持は既存公開フローに従う。
5. 検査は checkpoint を使う既存の eval 推論経路を通る。生成器は呼び出されず、結果形式は変わらない。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| `group_detail["<id>"].synthetic_anomaly` | 追加 | object、任意。`noise_std`、`perlin_threshold`、`perlin_scale_exponent` は各 `{min,max}` object、任意 | `0.010〜0.020`、`0.2〜0.4`、整数 `0〜5`。各範囲は両端を含む | 運用者が設定、共通設定が検証 | 旧設定の欠落は既定値で読めるが旧成果物は再利用しない |
| `noise_std` | 追加 | 有限な数値の端点 | `0 < min <= max`、真偽値を拒否 | 共通設定 | 移行なし |
| `perlin_threshold` | 追加 | 有限な数値の端点 | `0 <= min <= max < 1`、真偽値を拒否 | 共通設定 | 移行なし |
| `perlin_scale_exponent` | 追加 | 厳密な整数の端点 | `0 <= min <= max <= 5` | 共通設定 | 移行なし |
| checkpoint・最良試行・検査結果 | 維持 | 既存の保存契約 | 擬似異常を新しい探索パラメータとして保存しない | 既存の学習・評価 | 旧成果物との互換性は保証しない |

`config/part_XX.json` の各 `group_detail` に3項目の推奨値を明示し、他の値を変えない。README の設定項目表と用語集もコード・仕様の名称に合わせる。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 型番設定読込 | `train` CLI → 共通設定 | グループ詳細 | グループ別範囲 | 不正端点 → 入力不備、終了コード2、旧成果物保持 | 修正後に再実行 |
| 学習モデル生成 | 学習試行 → モデル adapter | グループ別範囲 | 差し替え済み生成器 | 生成失敗 → 既存の処理失敗と旧成果物保持 | 既存の新規探索として再実行 |
| 検査 | `test` CLI → 評価能力 | checkpoint と画像 | 既存形式の判定 | 既存仕様の入力不備・処理失敗・未判定 | 既存の再実行手順 |

## 技術判断

### 判断・候補: 生成器の差し替え位置

- **状態**: 確定。
- **採用内容**: Anomalib の `AnomalyGenerator` を継承し、学習モデル生成後に `model.model.anomaly_generator` を差し替える。設定は `create_supersimplenet` の任意引数とする。
- **根拠**: 指定された実装方針に合い、検査側の既存呼び出しには設定が不要である。
- **代替案**: Anomalib 本体の変更は依存更新で失われるため採用しない。
- **実装規則 / 不変条件**: 学習時だけ差し替える。生成器は既存の `model_adapter.py` 内に置き、`common/` から `model_training/` を import しない。checkpoint の読込みに新しい設定を要求しない。モデルの `state_dict` との整合を実ライブラリで確認する。
- **影響**: 共通のモデル生成境界と学習の呼び出し元を変更する。

### 判断・候補: mask 単位の乱数と生成手順

- **状態**: 確定。
- **採用内容**: `forward` の noise 生成と `generate_perlin` を派生クラスで実装し、標準正規 noise を mask ごとの標準偏差で拡大する。Perlin の縦横指数は `torch.randint(min, max + 1)` で独立に選ぶ。連続値は torch の一様乱数で選ぶ。
- **根拠**: 既存生成器は単一の標準偏差を batch 全体に使うため、mask ごとの強さには `forward` の変更が必要である。
- **代替案**: 親クラスの `forward` をそのまま使う案では mask ごとの noise 強度を実現できない。
- **実装規則 / 不変条件**: `min = max` は固定値。scale を範囲外へ丸めない。生成領域は各軸で scale の2倍以上とし、50% の適用判定と noise mask、label、特徴の更新順を親クラスと照合する。新しい Python/NumPy 乱数と seed 項目は使わない。
- **影響**: Anomalib 2.6.2 の生成器の該当ロジックを限定的に複製するため、依存更新時に照合が必要となる。

### 判断・候補: 学習 seed

- **状態**: 確定。
- **採用内容**: 既存 `group.optuna_settings.execution.seed` を試行開始時に torch に設定する。別の設定項目は作らない。
- **根拠**: 現状は同値を結果へ記録するが torch への明示適用が見つからない。利用者指定の「今の学習 seed」に対応させる。
- **代替案**: `sampler.seed` は探索候補の選択、`augmentation.seed` は画像拡張のための既存用途があるので混用しない。
- **実装規則 / 不変条件**: CPU と利用可能な GPU の torch 乱数列を同一条件内で再現可能にする。異なる機器間のビット単位一致は要求しない。
- **影響**: モデル初期化と学習中の torch 乱数系列が従来から変わるため再学習する。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 端点の範囲外、逆順、非有限値、真偽値、指数の小数 | 共通設定 | 学習開始前に拒否、旧成果物を保持 | 入力不備・終了コード2 | 既存 CLI の標準エラー | 設定修正後に再実行 |
| `min = max` | 擬似異常生成器 | 固定値として使用 | 学習は継続 | 自動試験で確認 | 不要 |
| 学習中の生成失敗 | 学習試行 | 旧公開成果物を保持 | 失敗グループと理由 | 既存の実行記録 | 原因修正後に再実行 |
| 旧成果物を使う操作 | 既存の整合確認 | 互換性を保証しない | 全工程の再実行を案内 | README | 旧成果物を引き継がず再生成 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | Pydantic の厳密な型と有限性・順序の検証 | 無効な設定は入力不備として拒否 |
| 性能 | mask ごとの乱数選択と Perlin 生成を追加 | 案件固有の速度目標は設定されていない。対象 OS の実行結果と所要時間を受け入れ証跡に記録 |
| 運用 | 設定例と README を更新し、全工程を再実行 | Ubuntu 24.04 LTS / Windows 11、CPU と利用可能な GPU の実測条件を記録 |
| 認証・認可 | 対象外。ローカル CLI の既存運用を維持 | 新しい権限境界なし |

## 移行とロールバック

1. 設定例と各型番設定の新項目を確認し、旧準備・学習・検査成果物を引き継がず `check`、`train-pre`、`train`、`test-pre`、`test` を順に実行する。
2. 完了判定は新しい設定で作成した成果物と検査結果の読戻し、および対象 OS での受け入れ確認とする。検出性能の本番判定は別途行う。
3. ロールバック時は変更前の設定とコードへ戻し、その状態に対応する成果物を再生成する。旧成果物との互換性に依存しない。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-032 | REQ-032-S01 | integration | 2グループで異なる固定範囲を読込み各モデルを生成 | 対象グループの値だけを使用 | `tests/test_model_adapter.py::test_synthetic_anomaly_uses_group_settings` | はい | 設定と学習モデルの接続、ローカル環境 | 実画像での両OS確認、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| TC-002 | REQ-032 | REQ-032-S02 | unit | 全体省略と一部省略を読込む | 所定の推奨値と明示値を得る | `tests/test_config.py::test_synthetic_anomaly_defaults` | はい | 設定読込、ローカル環境 | 実設定での両OS確認、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| TC-003 | REQ-033 | REQ-033-S01 | unit / integration | 固定 torch seed、非固定範囲で複数 mask を生成 | 範囲内、縦横独立、mask ごと、同一 seed で再現 | `tests/test_model_adapter.py::test_synthetic_anomaly_samples_per_mask` | はい | 実生成器と torch、ローカル CPU | 対象OS・GPU確認、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| TC-004 | REQ-033 | REQ-033-S02 | unit | 全範囲を固定値にして mask と特徴を生成 | 固定値、50% 判定、親クラス同等の合成・ラベル | `tests/test_model_adapter.py::test_synthetic_anomaly_preserves_generator_contract` | はい | Anomalib 2.6.2 との契約、ローカル CPU | 対象OS・GPU確認、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| TC-005 | REQ-034 | REQ-034-S01 | unit / integration | 範囲外、逆順、非有限値を読み込む | 入力不備、成果物保持、修正後の再実行 | `tests/test_config.py::test_synthetic_anomaly_rejects_invalid_bounds` | はい | 設定と CLI、ローカル環境 | 対象OSのCLI確認、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| TC-006 | REQ-034 | REQ-034-S02 | unit | 指数の小数と端点の真偽値を読込む | 入力不備、旧成果物保持 | `tests/test_config.py::test_synthetic_anomaly_rejects_invalid_types` | はい | 厳密な型、ローカル環境 | 対象OSのCLI確認、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| TC-007 | REQ-035 | REQ-035-S01 | integration | 範囲指定で探索候補・記録を確認 | 擬似異常条件は探索候補に現れない | `tests/test_training.py::test_synthetic_anomaly_is_not_search_parameter` | はい | 探索契約、ローカル環境 | 実学習での両OS確認、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| TC-008 | REQ-035 | REQ-035-S02 | integration | 設定付きモデルの checkpoint で推論 | 生成器不使用、既存形式の結果 | `tests/test_model_adapter.py::test_synthetic_anomaly_not_used_in_inference` | はい | 実モデル推論、ローカル CPU | 全CLI・両OSの読戻し、タスク4.2 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-032 | 2 | 2 | なし | 網羅 |
| REQ-033 | 2 | 2 | なし | 網羅 |
| REQ-034 | 2 | 2 | なし | 網羅 |
| REQ-035 | 2 | 2 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | グループ別設定、省略値、mask 単位の範囲選択 | TC-001〜TC-003 と対象OSの実学習 | 対象OSの実画像確認、タスク4.2 | 未検証 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| AC-002 | 全端点の境界・型、旧成果物保持と修正後再実行 | TC-005・TC-006 と対象OSのCLI | 対象OSのCLI確認、タスク4.2 | 未検証 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| AC-003 | 50% 判定、生成手順、torch seed | TC-003・TC-004 と対象OSの実学習 | 対象OSの実学習確認、タスク4.2 | 未検証 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| AC-004 | 探索条件と推論の分離、全工程再実行 | TC-007・TC-008 と全CLIの読戻し | 対象OSの全CLIと読戻し、タスク4.2 | 未検証 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
| AC-005 | Ubuntu 24.04 LTS / Windows 11、CPU と利用可能な GPU、実画像 | 実機スモークと成果物読戻し | 対象OSでの確認、タスク4.2 | 未検証 | openspec/changes/archive/2026-10-23-configure-synthetic-anomaly-generation/evidence/acceptance.md |
