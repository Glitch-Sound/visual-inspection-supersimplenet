## Context

既存実装は`src/app/__init__.py`の`main`が固定文字列を出力するだけのCLI雛形であり、画像処理、設定、学習、推論、結果保存の責務は存在しない。テストも挨拶出力だけを確認しているため、今回の変更では新しいCLIとドメイン処理を`src/app/`へ追加し、pytestで外部I/Oを含む境界を検証する。

`input.md`で定義された画像ディレクトリ、型番JSON、設定INI、Optuna SQLite、型番ごとの学習済みパラメータ、元画像単位の結果JSONを業務上の契約とする。モデルライブラリの具体的なバージョン選定と互換性検証は今回の設計対象外とし、モデル実行をアダプター境界で隔離する。

## Goals / Non-Goals

### Goals

- 型番設定を検証済みの内部データへ変換し、全CLIで共有する。
- 位置合わせ、分割、ブラックリスト、ファイル名対応を再現可能にする。
- 正常画像のみの初期学習と、将来の異常画像評価を交換可能な評価境界で支える。
- 分割画像スコアと元画像集約結果を、未判定・エラーを含めて追跡可能に保存する。
- CPU/GPU選択、seed、Optuna再開、ログを一貫して扱う。

### Non-Goals

- カメラ、製造ライン、Web UIの実装
- Anomalib、SuperSimpleNet、PyTorch、CUDAのバージョン決定
- 分割IDごとの個別モデル
- 異常画像のアノテーション作成

## Requirements Traceability

| 要件ID | 対応する設計節 | 実装対象 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | 設定・データ契約 | `config.py`, `schemas.py` | 2.1 | TC-001〜TC-002 | unit |
| REQ-002 | 画像準備 | `prepare.py`, `visualize.py` | 2.2 | TC-003 | integration |
| REQ-003 | 画像準備 | `prepare.py`, `filename.py` | 2.3 | TC-004〜TC-005 | integration |
| REQ-004 | 画像準備 | `prepare.py` | 2.4 | TC-006 | unit |
| REQ-005 | 位置合わせ・状態 | `alignment.py`, `manifest.py` | 2.5 | TC-007〜TC-008 | integration |
| REQ-006 | 学習データ | `dataset.py` | 2.6 | TC-009 | unit |
| REQ-007 | 学習データ | `augmentation.py`, `dataset.py` | 2.7 | TC-010〜TC-011 | unit |
| REQ-008 | 学習・探索 | `training.py`, `optimization.py` | 2.8 | TC-012 | integration |
| REQ-009 | 成果物 | `artifacts.py`, `training.py` | 2.9 | TC-013 | integration |
| REQ-010 | 探索管理 | `optimization.py` | 2.10 | TC-014 | integration |
| REQ-011 | 画像準備 | `prepare.py`, `manifest.py` | 2.11 | TC-015 | integration |
| REQ-012 | 推論 | `inference.py`, `threshold.py` | 2.12 | TC-016 | integration |
| REQ-013 | 結果集約 | `aggregation.py` | 2.13 | TC-017 | unit |
| REQ-014 | 結果保存 | `results.py` | 2.14 | TC-018〜TC-019 | integration |
| NREQ-001 | 実行環境 | `device.py`, `model_adapter.py` | 2.15 | TC-020 | integration |
| NREQ-002 | ログ | `logging.py`, CLI各コマンド | 2.16 | TC-021 | integration |
| NREQ-003 | 再現性 | `seed.py`, `dataset.py`, `optimization.py` | 2.17 | TC-022 | integration |

## Architecture and Responsibilities

### Component Map

| コンポーネント / ファイル候補 | 変更種別 | 責務 | 入力 | 出力・副作用 | 依存先 |
| --- | --- | --- | --- | --- | --- |
| `src/app/cli.py` | 追加 | `check`、`train-pre`、`train`、`test-pre`、`test`の引数と終了コードを管理 | CLI引数 | コマンド実行、ログ、終了コード | 各サービス |
| `src/app/config.py` | 追加 | INI/JSONを読み込み、型・範囲・必須項目を検証 | `config/setting.ini`, `config/part_XX.json` | 不変の設定モデル | `schemas.py` |
| `src/app/schemas.py` | 追加 | 設定、画像、分割、スコア、結果、状態の型を定義 | 辞書・パス | 型付きデータ | 標準ライブラリ |
| `src/app/filename.py` | 追加 | 元画像と分割画像の名前を生成・解析 | パス、分割ID | 対応付け情報 | `schemas.py` |
| `src/app/alignment.py` | 追加 | 基準画像への位置合わせと品質判定 | 画像、ORB設定 | 変換済み画像、品質、失敗理由 | 画像処理アダプター |
| `src/app/prepare.py` | 追加 | 学習・試験画像の位置合わせ、ブラックリスト、切り出し | 元画像、設定 | 分割画像、準備マニフェスト | `config`, `alignment`, `filename` |
| `src/app/visualize.py` | 追加 | 分割矩形とIDを基準画像へ描画 | 基準画像、範囲 | `data/03_check/XX.png` | 画像I/O |
| `src/app/manifest.py` | 追加 | 準備結果、失敗、警告を元画像単位で記録 | 準備イベント | 学習・試験準備マニフェスト | `schemas.py`, `logging` |
| `src/app/dataset.py` | 追加 | 元画像単位のsplitと学習・検証入力を提供 | 分割画像、名前、seed | train/validationデータセット | `filename`, `augmentation` |
| `src/app/augmentation.py` | 追加 | 学習時だけ設定済み拡張を適用 | 画像、拡張設定、乱数 | 一時的な学習入力 | 画像処理アダプター |
| `src/app/model_adapter.py` | 追加 | 外部モデル実装との境界、学習・推論・ヒートマップ | データセット、学習条件 | 学習済みモデル、スコア、マップ | 外部モデルライブラリ |
| `src/app/optimization.py` | 追加 | Optunaのstudy、探索空間、seed、再開、評価 | 学習・検証データ | 最良条件、評価値、SQLite | `training`, `model_adapter` |
| `src/app/training.py` | 追加 | 学習、閾値算出、成果物保存を調整 | 設定、データ、探索条件 | `weights/XX.ckpt`, metadata | `dataset`, `optimization`, `artifacts` |
| `src/app/threshold.py` | 追加 | 学習用正常画像スコアの99パーセンタイルを算出 | スコア列 | 型番閾値 | `schemas.py` |
| `src/app/inference.py` | 追加 | 分割画像の推論と閾値判定を調整 | 分割画像、モデル、閾値 | 分割結果 | `model_adapter`, `threshold` |
| `src/app/aggregation.py` | 追加 | 分割結果を元画像結果へ集約 | 分割結果、準備状態 | `normal/anomaly/undetermined` | `schemas.py` |
| `src/app/results.py` | 追加 | ヒートマップ画像と元画像単位JSONを保存 | 推論結果、マニフェスト | `data/06_result/XX/` | `schemas.py`, `filename` |
| `src/app/device.py` | 追加 | GPU利用可否を判定し実行デバイスを選択 | 実行環境 | GPUまたはCPU | モデルアダプター |
| `src/app/logging.py` | 追加 | 経過、処理時間、警告、エラーを統一出力 | イベント | 利用者向けログ | `loguru` |

### Processing Flow

1. CLIが`--model XX`を受け取り、設定ローダーがINI/JSONを検証する。失敗時は生成物を作らず非ゼロ終了する。
2. `check`は基準画像を読み込み、各分割範囲を境界検証して矩形とIDを描画する。
3. `train-pre`と`test-pre`は、元画像を読み込み、基準画像への位置合わせ品質を判定する。
4. 学習準備で位置合わせに失敗した元画像は警告付きで除外し、試験準備で失敗した元画像は未判定状態としてマニフェストに記録する。
5. 成功した画像は、OpenCV座標の左上包含・右端下端非包含で`SIZE x SIZE`に切り出し、`stem_nn.png`で保存する。範囲外なら該当出力を作らずエラーにする。
6. `train`はブラックリスト適用済み分割画像を元画像stemでグループ化し、seed 42で元画像単位に80/20分割する。
7. 学習データだけに型番設定の拡張を適用し、モデルアダプターで全分割IDを同一モデルに入力する。
8. Optunaは50試行を上限に学習・検証を繰り返し、検証スコアの99パーセンタイルを最小化する。studyはSQLiteへ保存し、既存studyは再開する。
9. 最良試行で学習済みパラメータを確定し、学習用正常スコアの99パーセンタイルを型番閾値としてmetadataとともに保存する。
10. `test`は試験マニフェストの未判定状態を先に結果へ反映し、実行可能な分割画像だけを同一モデルで推論する。
11. 分割画像スコアが閾値以上なら`anomaly`、未満なら`normal`とし、異常が1つでもあれば元画像を`anomaly`、全て正常なら`normal`、未判定が残り異常がない場合は`undetermined`とする。
12. 結果保存器は分割画像の結果画像、異常時のヒートマップ、元画像単位JSONを保存し、処理時間・警告・エラーを記録する。

### State and Data Design

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番設定 | 追加 | `base: string`, `range: list`, `blacklist: list`, `optuna_settings: object`, `augmentation: object`, `alignment: object` (required) | `SIZE`は正方形、ORB minimum 20、confidence 0.5 | 設定ローダー | 新規形式、旧設定なし |
| 分割画像名 | 追加 | `source_stem: string`, `part_id: int`, `path: string` (required) | `stem_nn.png`、IDは2桁0埋め | ファイル名サービス | 元画像stemとの対応を維持 |
| 準備マニフェスト | 追加 | `source_image`, `status`, `parts`, `warnings`, `errors` (required) | statusは`ready`または`undetermined` | 準備サービス | `data/05_test/XX/_preparation.json`を試験入力とする |
| 学習metadata | 追加 | `model_path`, `threshold`, `percentile`, `best_params`, `objective`, `seed` (required) | percentile 99、seed 42 | 学習サービス | `weights/XX.json`等でモデルと対応付け |
| 分割検査結果 | 追加 | `part_id`, `image`, `score`, `result`, `heatmap`, `alignment`, `errors`, `warnings` | scoreは未判定時`null`、resultは4状態 | 結果保存器 | 元画像JSONに内包 |
| 元画像検査結果 | 追加 | `source_image`, `model`, `threshold`, `parts`, `overall_result`, `processed_at` (required) | overallは`normal/anomaly/undetermined` | 結果保存器 | `data/06_result/XX/<stem>.json` |
| Optuna study | 追加 | trial、params、objective、seed (required) | `optuna/XX/study.db`、50試行、再開 | 探索サービス | 既存DBを保持 |

### Interfaces and Error Handling

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `check --model XX` | CLI → 可視化サービス | 型番、設定、基準画像 | 確認画像 | 設定不正・基準画像なし → エラー、出力なし | 同じ入力で上書き可能 |
| `train-pre --model XX` | CLI → 準備サービス | 学習元画像 | 分割画像、マニフェスト、警告 | ORB失敗 → 除外・警告、範囲外 → エラー | 出力ディレクトリを型番単位に再生成 |
| `train --model XX` | CLI → 学習サービス | 分割画像、設定、study | checkpoint、metadata、study | データ不足・学習失敗 → エラー、既存study保持 | SQLiteから再開、既存成果物を無断上書きしない |
| `test-pre --model XX` | CLI → 準備サービス | 試験元画像 | 分割画像、準備マニフェスト | ORB失敗 → エラー明示・未判定記録、範囲外 → エラー | 元画像単位で再実行可能 |
| `test --model XX` | CLI → 推論・結果サービス | 分割画像、マニフェスト、checkpoint、metadata | 結果画像、JSON | モデル不足・設定不正 → エラー、未判定入力 → JSONへ記録 | 同一入力で結果を再生成可能 |
| モデル推論 | 推論サービス → モデルアダプター | 画像バッチ | スコア、ヒートマップ | 外部モデル失敗 → 分割error、処理ログ、元画像undetermined | バッチ単位で再試行可能 |

## Decisions

### Decision: 1モデルで全分割IDを処理する

- **採用**: 型番ごとに1つの学習済みパラメータへ全分割画像を入力する。
- **根拠**: 分割画像ごとのモデル管理を避け、利用者が指定する成果物を型番単位に保つ。
- **代替案と不採用理由**: 分割IDごとのモデル — モデル数と運用負荷が増えるため初期範囲から除外する。
- **実装規則 / 不変条件**: 分割IDをモデルファイル名や成果物の識別子にしてはならない。
- **影響**: 分割位置の分布差は同一モデルの評価結果で確認し、性能不足時は別changeで再検討する。

### Decision: 正常画像初期評価は99パーセンタイルで行う

- **採用**: Optuna目的値は検証用正常画像スコアの99パーセンタイル、判定閾値は学習用正常画像スコアの99パーセンタイルとする。
- **根拠**: 異常画像がない段階でも正常画像の誤検出リスクを測定できる。
- **代替案と不採用理由**: 異常画像のF1や再現率 — 初期入力に異常画像がないため使用できない。
- **実装規則 / 不変条件**: 探索評価用データと閾値算出用データを混同しない。
- **影響**: 異常画像導入後は評価関数と閾値探索を拡張する。

### Decision: 位置合わせ失敗は学習除外、試験未判定とする

- **採用**: 学習では失敗画像を除外して警告し、試験ではエラーと未判定を結果JSONへ残す。
- **根拠**: 誤った位置で学習データを汚染せず、試験時に見逃し扱いで消失させない。
- **代替案と不採用理由**: 未位置合わせ画像で継続 — 学習・検査結果の信頼性を損なうため採用しない。
- **実装規則 / 不変条件**: 失敗画像を正常・異常の確定判定へ変換しない。
- **影響**: 未判定件数と理由をログ・JSONで追跡する。

### Decision: 外部モデル実装をアダプターで隔離する

- **採用**: 学習・推論サービスは内部の画像・スコア契約だけを扱い、Anomalib等の呼び出しをモデルアダプターに限定する。
- **根拠**: バージョン互換性を後続工程で検証・変更できるようにする。
- **代替案と不採用理由**: CLIやデータセットへ直接呼び出し — 依存変更の影響範囲が広がるため採用しない。
- **実装規則 / 不変条件**: アダプターは画像スコア、ヒートマップ、学習済み成果物を内部契約へ変換する。
- **影響**: 互換性検証は別途必要だが、業務ロジックのテストはモデル実装から分離できる。

## Edge Cases and Failure Modes

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 設定ファイルなし・不正 | 設定ローダー | 処理開始前に停止 | エラー終了、生成物なし | 型番、項目、理由 | 設定修正後に再実行 |
| 基準画像なし・破損 | 準備サービス | 該当コマンド停止 | エラー終了 | パス、例外 | 入力差替え後に再実行 |
| ORB品質不足 | 位置合わせサービス | 学習除外、試験未判定 | 学習は継続、試験は未判定 | マッチ数、信頼度、理由 | 閾値調整または画像再撮影 |
| 分割範囲外 | 設定検証・切り出し | 該当出力なし | エラー終了 | 範囲、画像サイズ | 設定修正 |
| 学習データ不足 | datasetサービス | 学習を開始しない | 必要枚数と実数をエラー表示 | 型番、件数 | データ追加 |
| 全試行失敗 | 探索サービス | 既存studyを保持 | エラー終了 | trial失敗理由 | 条件修正・再開 |
| GPU利用不可 | deviceサービス | CPUへ切替 | 処理継続 | 選択デバイス、理由 | CPUのまま再実行 |
| モデル成果物なし | 推論サービス | 推論を開始しない | エラー終了 | 型番、期待パス | 学習成果物を生成 |
| 既存study | 探索サービス | 新規上書きせず再開 | 継続結果を表示 | study名、件数 | 明示的な別study名で新規作成 |
| 結果保存失敗 | 結果サービス | 一時出力を確定しない | エラー終了 | パス、例外 | 空き容量・権限修正後再実行 |

## Security, Performance, and Operations

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 設定値、パス、範囲、画像形式、JSON状態値を検証する | 不正入力で処理開始せず、理由をログに残す |
| 機密情報 | 画像・モデル・ログに秘密情報を追加しない | repository checkとログ確認 |
| メモリ | 大画像を必要な処理単位で読み込み、分割後に参照を解放する | CPU環境でサンプル画像を完走する |
| 性能 | 各CLIで処理時間と件数をログに出す | 入力件数、成功、除外、未判定、経過時間を確認できる |
| 再現性 | seed 42、設定、study、metadataを保存する | 同一入力で分割・探索条件が一致する |
| 運用 | 型番ごとのstudyとweightsを分離し、既存結果を保持する | 再開時に既存trialが消えない |

## Migration and Rollback

既存のアプリケーションは挨拶を出力するだけで、移行対象の画像データ、設定、公開API、永続データを持たないため、既存データの移行は不要である。実装中に生成した検査用ディレクトリと成果物は、型番単位で削除して再生成できる。コード変更のロールバック時は、新規CLIと外観検査用データを利用しない状態へ戻す。

## Test Design

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-001 | REQ-001-S01 | unit | 有効な設定を読み込む | 型番設定が内部モデルになる | `tests/test_config.py::test_load_valid_part_config` | はい |
| TC-002 | REQ-001 | REQ-001-S02 | unit | 不正な範囲設定を読み込む | 設定エラーで停止する | `tests/test_config.py::test_reject_invalid_range` | はい |
| TC-003 | REQ-002 | REQ-002-S01 | integration | 基準画像と複数範囲で`check` | 確認画像に矩形とIDが出力される | `tests/test_prepare.py::test_check_outputs_overlay` | はい |
| TC-004 | REQ-003 | REQ-003-S01 | integration | 学習元画像で`train-pre` | `xxx_nn.png`が出力される | `tests/test_prepare.py::test_prepare_train_parts` | はい |
| TC-005 | REQ-003 | REQ-003-S02 | unit | 範囲外の分割を実行 | 分割画像を作らずエラーになる | `tests/test_prepare.py::test_reject_out_of_bounds_crop` | はい |
| TC-006 | REQ-004 | REQ-004-S01 | unit | ブラックリスト対象を準備 | 対象IDだけ出力されない | `tests/test_prepare.py::test_apply_blacklist` | はい |
| TC-007 | REQ-005 | REQ-005-S01 | integration | 学習用ORB品質不足 | 除外と警告が記録される | `tests/test_alignment.py::test_train_alignment_failure_excluded` | はい |
| TC-008 | REQ-005 | REQ-005-S02 | integration | 試験用ORB品質不足 | エラーと未判定マニフェストが残る | `tests/test_alignment.py::test_test_alignment_failure_undetermined` | はい |
| TC-009 | REQ-006 | REQ-006-S01 | unit | 元画像グループをseed 42でsplit | 同一stemの分割が同じ側になる | `tests/test_dataset.py::test_split_by_source_image` | はい |
| TC-010 | REQ-007 | REQ-007-S01 | unit | 拡張有効で学習datasetを取得 | 元ファイルを変更せず拡張入力になる | `tests/test_augmentation.py::test_train_only_augmentation` | はい |
| TC-011 | REQ-007 | REQ-007-S02 | unit | validation/test datasetを取得 | 入力が拡張されない | `tests/test_augmentation.py::test_disable_augmentation_for_eval` | はい |
| TC-012 | REQ-008 | REQ-008-S01 | integration | 正常画像でOptunaを実行 | 99パーセンタイル最小trialが選ばれる | `tests/test_optimization.py::test_minimize_normal_percentile` | はい |
| TC-013 | REQ-009 | REQ-009-S01 | integration | 最良trialの学習を完了 | weights、閾値、metadataが対応保存される | `tests/test_training.py::test_save_training_artifacts` | はい |
| TC-014 | REQ-010 | REQ-010-S01 | integration | 既存SQLite studyで再実行 | 既存trialを保持して再開する | `tests/test_optimization.py::test_resume_existing_study` | はい |
| TC-015 | REQ-011 | REQ-011-S01 | integration | 試験元画像で`test-pre` | 全分割が保存されブラックリストを無視する | `tests/test_prepare.py::test_prepare_test_parts` | はい |
| TC-016 | REQ-012 | REQ-012-S01 | integration | スコアと閾値で`test` | 各分割にscoreとnormal/anomalyが付く | `tests/test_inference.py::test_classify_part_score` | はい |
| TC-017 | REQ-013 | REQ-013-S01 | unit | normal/anomalyの分割結果を集約 | 元画像がanomalyになる | `tests/test_aggregation.py::test_any_anomaly_marks_source_anomaly` | はい |
| TC-018 | REQ-014 | REQ-014-S01 | integration | 正常・異常推論を保存 | 結果画像、ヒートマップ、JSONが保存される | `tests/test_results.py::test_save_inspection_result` | はい |
| TC-019 | REQ-014 | REQ-014-S02 | integration | 未判定マニフェストを保存 | null scoreとundeterminedがJSONに残る | `tests/test_results.py::test_save_undetermined_result` | はい |
| TC-020 | NREQ-001 | NREQ-001-S01 | integration | GPUなしで実行 | CPUへ切り替わり処理が完了する | `tests/test_device.py::test_cpu_fallback` | はい |
| TC-021 | NREQ-002 | NREQ-002-S01 | integration | CLIを成功・失敗実行 | 型番、結果、時間、生成物、警告・エラーが出る | `tests/test_cli.py::test_cli_reports_processing_summary` | はい |
| TC-022 | NREQ-003 | NREQ-003-S01 | unit | 同じ入力とseedでsplit設定を生成 | 同じsplitと探索設定になる | `tests/test_reproducibility.py::test_seed_reproduces_split` | はい |

## Coverage Confirmation

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | ---: | ---: | --- | --- |
| REQ-001 | 2 | 2 | なし | 網羅 |
| REQ-002 | 1 | 1 | なし | 網羅 |
| REQ-003 | 2 | 2 | なし | 網羅 |
| REQ-004 | 1 | 1 | なし | 網羅 |
| REQ-005 | 2 | 2 | なし | 網羅 |
| REQ-006 | 1 | 1 | なし | 網羅 |
| REQ-007 | 2 | 2 | なし | 網羅 |
| REQ-008 | 1 | 1 | なし | 網羅 |
| REQ-009 | 1 | 1 | なし | 網羅 |
| REQ-010 | 1 | 1 | なし | 網羅 |
| REQ-011 | 1 | 1 | なし | 網羅 |
| REQ-012 | 1 | 1 | なし | 網羅 |
| REQ-013 | 1 | 1 | なし | 網羅 |
| REQ-014 | 2 | 2 | なし | 網羅 |
| NREQ-001 | 1 | 1 | なし | 網羅 |
| NREQ-002 | 1 | 1 | なし | 網羅 |
| NREQ-003 | 1 | 1 | なし | 網羅 |
