## 背景・前提

現行実装は `src/app/__init__.py` の挨拶表示と、その単体テストだけである。`pyproject.toml` は Python 3.13、src レイアウト、Typer、Loguru、Pydantic Settings を採用しているが、画像処理、機械学習、探索、GPU 実行の依存関係と CLI は未登録である。`uv.lock` にも PyTorch、torchvision、Anomalib、Optuna、OpenCV は含まれず、既存の正式仕様と永続データはない。

実装はローカル CLI とファイルシステムを境界とし、撮影装置、ネットワークサービス、認証・認可は対象外とする。元画像を不変入力として扱い、設定、派生画像、学習済みパラメータ、探索履歴、検査結果を型番単位で管理する。

2026-10-03 時点の公式情報では、PyTorch 2.13.0 と torchvision 0.28.0 の CUDA 13.0 wheel が Linux / Windows 向けに提供され、torchvision の互換表は Python 3.10〜3.14 を対象としている。Anomalib 2.6.2 は `py3-none-any` wheel を提供し、同版のドキュメントに SuperSimpleNet 実装がある。CUDA 13.0 の最低ドライバは Linux 580.65.06、Windows 580.88 である。これらを初期固定候補として採用し、実機スモーク試験の結果を運用記録へ残す。

参照:

- https://pytorch.org/get-started/previous-versions/
- https://pypi.org/project/torchvision/
- https://pypi.org/project/anomalib/2.6.2/
- https://anomalib.readthedocs.io/en/lib-v2.6.2/markdown/guides/reference/models/image/supersimplenet.html
- https://docs.nvidia.com/datacenter/tesla/tesla-release-notes-580-65-06/

## 目標・対象外

### 目標

- 5つの型番指定 CLI（`check`、`train-pre`、`train`、`test-pre`、`test`）を同一の設定・ログ・終了状態契約で提供する。
- ORB 位置合わせ、範囲検証、ブラックリスト、元画像と分割画像の追跡を純粋な契約と責務境界に分け、固定画像で自動試験できるようにする。
- SuperSimpleNet の学習・推論をアダプタ境界へ隔離し、Optuna の探索、元画像単位分離、学習時限定データ拡張、再開をテストダブルで検証可能にする。
- 型番別の単一モデル、暫定閾値、探索履歴、分割結果、元画像集約結果を機械可読かつ再現可能に保存する。
- GPU 優先・CPU フォールバックを実装し、Ubuntu 24.04 LTS / Windows 11 の実機スモーク試験手順と記録形式を固定する。

### 対象外

- 初期モデルの本番精度・処理時間目標の決定、および本番利用承認。
- 異常ラベルを用いた教師あり評価、閾値・データ拡張を含む同時最適化。
- GUI、Web API、撮影装置・通知サービスとの連携、複数利用者向け認証・認可。
- 旧成果物の長期保管・世代管理。明示的な再生成前の任意退避は運用手順に委ねる。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | 業務フローと責務 / インターフェースと失敗時の結果 / 判断 2 | 設定、座標検証、確認画像、基準画像パス制約 | 1.2, 1.5, 2.1, 4.1, 4.6 | TC-001〜TC-002, TC-031 | 設定・画像統合テスト |
| REQ-002 | 業務フローと責務 / 処理フロー 2 | 学習準備、位置合わせ、ブラックリスト、I/O失敗 | 1.2, 2.2, 3.11, 4.2, 4.7 | TC-003〜TC-006, TC-035〜TC-036, TC-038 | 固定画像統合テスト |
| REQ-003 | 業務フローと責務 / 処理フロー 4 | 試験準備、未判定引き継ぎ、I/O失敗 | 1.2, 2.3, 3.11, 4.2, 4.7 | TC-007〜TC-009, TC-039 | 固定画像統合テスト |
| REQ-004 | 処理フロー 3 / 判断 2 / 判断 4 | 型番・ファイル名・対応関係を検証した元画像単位データ分離 | 3.1, 3.12, 4.3, 4.8 | TC-010〜TC-011, TC-040 | 分離ロジック・manifest契約テスト |
| REQ-005 | 処理フロー 3 / 判断 5 / 判断 10 | 探索・暫定指標・スコア契約 | 1.2, 1.5, 3.2, 4.3 | TC-012〜TC-013 | 探索アダプタ統合テスト |
| REQ-006 | 判断 6 | 学習時データ拡張 | 1.2, 3.3, 4.3 | TC-014〜TC-015 | 変換境界単体テスト |
| REQ-007 | データ契約と状態 / 判断 3 / 判断 7 / 判断 10 | モデル、スコア契約、閾値、型付き探索成果物、一式更新 | 1.2, 3.4, 3.11, 3.12, 4.3, 4.7, 4.8 | TC-016〜TC-017, TC-037, TC-041 | ファイル契約統合テスト |
| REQ-008 | インターフェースと失敗時の結果 / 判断 7 | 探索再開・再学習 | 3.5, 4.3 | TC-018〜TC-019 | SQLite・削除範囲統合テスト |
| REQ-009 | 判断 8 | デバイス選択 | 1.3, 4.4 | TC-020〜TC-021 | デバイス検出単体テスト |
| REQ-010 | 処理フロー 5 / 判断 3 / 判断 10 | 共通決定的前処理、推論、スコア契約、閾値判定、可視化 | 1.2, 3.6, 3.11, 4.4, 4.7 | TC-022〜TC-023, TC-033 | 推論アダプタ統合テスト |
| REQ-011 | 判断 9 | 元画像判定集約 | 3.7, 4.4 | TC-024〜TC-026 | 判定組合せ単体テスト |
| REQ-012 | データ契約と状態 / 判断 2 / 判断 7 / 判断 10 | 安全なmanifest、一意な成果物名、スコア契約と型付き実行記録を含む検査結果 JSON | 1.4, 1.6, 3.8, 3.10, 3.11, 3.12, 4.4, 4.6, 4.7, 4.8 | TC-027, TC-032, TC-034, TC-042 | JSON スキーマ統合テスト |
| REQ-013 | インターフェースと失敗時の結果 / 判断 7 | 明示的な再検査 | 3.9, 4.4 | TC-028 | 削除範囲統合テスト |
| NREQ-001 | セキュリティ・性能・運用 | 依存関係、OS、実行記録 | 1.1, 4.5 | TC-029〜TC-030 | CI と対象実機スモーク試験 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| CLI 調停 | 追加 | コマンド、`--model`、`--restart` | 終了コード、構造化ログ、処理時間 | 全ユースケース | `src/app/cli.py` の5エントリポイントで確定 |
| 設定・パス解決 | 追加 | `setting.ini`、`part_<model>.json`、型番 | 検証済み設定と型番配下パス | Pydantic、標準ライブラリ | `src/app/config.py`、`src/app/paths.py` で確定 |
| 画像位置合わせ・分割 | 追加 | 基準画像、元画像、分割範囲 | 変換済み画像、分割画像、位置合わせ結果 | OpenCV | `src/app/imaging.py` と `src/app/preparation.py` で確定 |
| 学習データ構成 | 追加 | 学習 manifest、比率、seed | 元画像単位の train / validation 集合 | ファイル契約 | `src/app/training.py` 内の独立関数で確定 |
| モデル・探索境界 | 追加 | 探索条件、学習・検証集合、デバイス | 試行結果、最良 checkpoint、PostProcessor適用前`pred_score` | Anomalib、PyTorch、Optuna | `src/app/modeling.py` のアダプタと `src/app/training.py` の調停で確定 |
| 推論・結果集約 | 追加 | checkpoint、スコア契約、閾値、試験 manifest | 分割判定、ヒートマップ、元画像判定 | モデル境界、画像処理 | `src/app/evaluation.py`、`src/app/results.py` で確定 |
| デバイス・実行記録 | 追加 | GPU 利用可否、パッケージ版 | 選択デバイス、理由、運用記録 | PyTorch、Loguru | `src/app/runtime.py` で確定 |

### 処理フロー

1. CLI は `--model` を検証し、全体設定と型番設定を読み、型番から許可されたデータルートだけを解決する。入力不備は処理開始前に終了コード2で返す。
2. `check` は基準画像と全分割範囲を検証して確認画像をステージング先へ生成し、成功時に置換する。`train-pre` は各学習元画像を ORB で位置合わせし、ブラックリストを除外して分割画像と manifest をステージング先へ生成する。ORBは最低20対応点、RANSAC再投影誤差3.0px、RANSAC信頼確率0.995でホモグラフィを推定し、返却マスクのインライア比率0.5以上を成功とする。位置合わせ失敗は元画像名・理由・再確認案内を含む警告付き除外、範囲外は元画像名と分割IDを含む実行全体のエラー、画像I/O失敗は終了コード3とする。
3. `train` は manifest を元画像単位で train / validation に分け、学習集合だけに設定済みデータ拡張を適用する。Optuna は型番から決定した `optuna/<model>/study.db` の既存 study を再利用し、モデルに設定した単一の決定的前処理と、SuperSimpleNetが返すPostProcessor適用前`pred_score`を用いて検証集合の99パーセンタイルを最小化する。完了時に最良モデルをデータ拡張なしで学習集合へ再推論し、同じ`pred_score`の99パーセンタイルを暫定閾値として、最良checkpoint、探索結果、スコア契約、環境情報を全件ステージング後にトランザクション記録付きで置換する。失敗・中断時は次回開始前までに旧一式を復旧する。
4. `test-pre` はブラックリストを無視し、学習準備と同じORB成功条件で試験元画像を処理する。位置合わせ失敗は manifest に `undetermined` と理由を残し、元画像名・理由・未判定・再撮影案内を警告する。範囲外は元画像名と分割IDを含む実行全体のエラー、画像I/O失敗は終了コード3とする。成功時に試験分割画像と manifest を置換する。
5. `test` は未完了の成果物トランザクションを旧一式へ復旧してからモデル、スコア契約、閾値を読み、利用可能なら GPU、利用不能なら CPU を選ぶ。モデルに設定した学習・閾値算出と同じ決定的前処理を全分割へ適用し、`pred_score >= threshold` を異常とする。正常画像は内容を変えず結果領域へ保存し、異常画像はPostProcessor適用前`anomaly_map`を用いたヒートマップを保存する。JSONと結果画像は拡張子付き入力名を含む名前で一意に保存する。
6. 結果集約は `anomaly` を最優先し、全分割 `normal` のときだけ `normal`、それ以外を `undetermined` とする。元画像単位 JSON は成功・未判定・エラーのいずれでも原子的に保存し、評価者が次の処置を判断できるようにする。
7. `--restart` を伴う `train` は対象型番の `optuna/<model>/` と `weights/<model>.ckpt` だけを、`test` は `data/06_result/<model>/` だけを削除して再生成する。削除前に対象パスが解決済みルート直下であることを検証する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| `config/setting.ini` | 追加 | `IMAGE.SIZE: int` | 正数、正方形、一辺500pxを初期値。初期テンプレートはインラインコメントを含まない `SIZE = 500` | 運用者 | 新規。未知キーは警告、必須欠落はエラー |
| `config/part_<model>.json` | 追加 | `base: str`、`range[]: {id:int,x:int,y:int}`、`blacklist[]`、`optuna_settings`、`score`、`augmentation`、`alignment` | `base`はパス要素を含まないファイル名。型番は安全な識別子、IDは0〜99で一意、比率合計1、目的値・閾値percentile=99、trials=50、seed=42。study保存先は設定に持たず`optuna/<model>/study.db`へ固定。`score.source == threshold.score_source`かつPostProcessor無効。ORB初期値は最低20対応点、再投影誤差3.0px、RANSAC信頼確率0.995、最低インライア比率0.5 | 運用者。学習完了時は `threshold.value` をcheckpoint・最良試行結果と同じトランザクションで更新 | 新規。Pydantic で全体検証し不明な破壊的形式を拒否 |
| 準備 manifest | 追加 | `model: str`、`created_at: datetime`、`sources[]: {source_image, alignment, splits[]}`、`splits[]: {source_image, split_id, image}`、`excluded[]` | 型番は要求型番と一致。画像名はパス要素のない単一ファイル名。元画像名と分割画像名はmanifest内で一意、分割IDは親元画像内で一意、分割の`source_image`は親と一致。`alignment.status`は`aligned`、`failed`、`undetermined`。日時はタイムゾーン付き。UTF-8 JSON | preparation | `data/04_train/<model>/manifest.json` と `data/05_test/<model>/manifest.json`。不正時は後続処理開始前に拒否 |
| 学習済みパラメータ | 追加 | checkpoint と型番・スコア契約・暫定閾値 | `weights/<model>.ckpt`。全分割共通。スコア源は`supersimplenet.pred_score`、PostProcessor無効 | training/modeling | 新規。異なる型番またはスコア契約の流用を拒否 |
| Optuna study | 追加 | study DB、試行条件、指標、状態 | `optuna/<model>/study.db`、方向minimize、TPE seed 42、MedianPruner、枝刈り・失敗を含む合計50試行 | training | 通常実行は再開、`--restart` のみ置換 |
| 最良試行結果 | 追加 | trial番号、型付き探索条件、objective、checkpoint、score_contract、threshold、データ集合、seed、依存版 | `optuna/<model>/best_trial.json`。型番・checkpoint参照・スコア契約・閾値は要求型番のcheckpoint・型番設定と同値 | training | 新規。不整合または不正な探索条件はモデル生成前に拒否 |
| 事前学習重み | 追加 | `wide_resnet50_2.tv_in1k` のキャッシュ | `pretrained/`、存在時は再取得しない | modeling | 再学習で削除しない |
| 分割検査結果 | 追加 | `split_id:int`、`image:str`、`score:float|null`、`status: enum`、`result_image:str|null`、`error:str|null` | scoreはPostProcessor適用前`pred_score`、statusは normal/anomaly/undetermined/error | evaluation | 新規 |
| 元画像検査結果 | 追加 | `source_image`、`model`、`checkpoint`、`score_contract`、`threshold`、`splits[]`、`overall_status`、`processed_at`、`alignment`、`errors[]`、`warnings[]`、`runtime: RunMetadata` | `score_contract.source`は`supersimplenet.pred_score`、PostProcessorはfalse。日時はタイムゾーン付き。元画像ごとに `data/06_result/<model>/<source_image>.json`、分割結果画像は`<split_image>_result.png`として拡張子付き入力名を含める | results | 新規。同じstem・異拡張子でも一意。必須項目・列挙値・日時・実行記録の不正を許さない |
| 実行記録 | 追加 | command、開始終了時刻、コマンド単位のduration、exit status、OS、Python、主要依存版、device、warnings/errors | 秘密情報と画像内容を含めない。画像単位の処理時間は初期要件に含めない | runtime/CLI | 全CLIは標準出力、検査は`data/06_result`の元画像JSON、実機確認はスモーク結果JSONへ保存 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `check --model` | 運用者 → 画像確認 | 安全な型番 | 確認画像、exit 0 | 設定不備・範囲外 → 対象項目表示、exit 2、不完全出力なし | 同一入力で置換可能 |
| `train-pre --model` | 運用者 → 学習準備 | 設定、学習元画像 | 分割画像、manifest、exit 0/警告 | ORB失敗 → 画像単位除外。範囲外・I/O失敗 → exit 3、現行一式維持 | ステージング後に原子的置換 |
| `train --model [--restart]` | 運用者 → 学習・探索 | manifest、探索設定 | checkpoint、study、最良結果、閾値 | データ不足・設定不備 → 開始前exit 2。学習失敗 → 試行失敗を記録してexit 3 | 通常はstudy再開。restartのみ対象成果物削除 |
| `test-pre --model` | 運用者 → 試験準備 | 設定、試験元画像 | 分割画像、未判定を含むmanifest | ORB失敗 → 未判定を保存。範囲外・I/O失敗 → exit 3 | ステージング後に原子的置換 |
| `test --model [--restart]` | 運用者 → 推論・集約 | manifest、checkpoint、スコア契約、閾値 | 結果画像と元画像JSON | モデル・スコア契約・閾値の不足または不一致 → exit 2。画像単位失敗 → error/undetermined JSON、他画像は継続 | restartのみ対象結果一式を置換 |
| 事前学習重み取得 | modeling → 配布元/キャッシュ | backbone ID | キャッシュ済み重み | ネットワーク・整合性失敗 → 学習中止、再実行案内 | キャッシュ優先。ライブラリ既定timeoutを記録 |

## 技術判断

### 判断 1: CLI とモジュール境界

- **状態**: 確定
- **採用内容**: Typer の独立 console script 5本を `src/app/cli.py` へ置き、設定、画像準備、モデル境界、学習、評価、結果、実行環境を別モジュールへ分離する。
- **根拠**: 入力資料の `uv run <command> --model` 契約を維持し、重い依存境界を単体試験から置換可能にするため。
- **代替案**: 単一サブコマンドアプリは操作契約が変わるため不採用。全処理をCLI関数へ集約する案は試験性が低いため不採用。
- **実装規則 / 不変条件**: CLI は調停だけを行い、業務判断を持たない。各コマンドは結果、コマンド単位の処理時間、警告・エラー、終了コードを型付き実行記録として標準出力へ返す。`test`は推論・集約後に実行記録を確定し、同じ記録を各元画像結果JSONへ保存する。
- **影響**: `pyproject.toml` の scripts と `src/app/` を拡張する。

### 判断 2: 設定検証と座標契約

- **状態**: 確定
- **採用内容**: INI を全体設定、JSON を型番設定として Pydantic モデルへ読み込み、処理前に相互検証する。`IMAGE.SIZE` はコメントを含まない値全体を10進整数へ変換する。型番は `^[A-Za-z0-9][A-Za-z0-9_-]*$` に制限し、基準画像`base`はディレクトリを含まないファイル名に制限する。
- **根拠**: 型不正、範囲外、パストラバーサルを処理開始前に検出し、OS間で同じ契約にするため。
- **代替案**: 辞書を都度参照する案はエラー箇所と既定値が不明確になるため不採用。
- **実装規則 / 不変条件**: `setting.ini` の初期テンプレートは `[IMAGE]` の `SIZE = 500` とし、値と同じ行にコメントを置かない。`SIZE` は正の整数として検証する。`base`およびmanifest・結果契約内の画像名は絶対パス、`.`、`..`、パス区切り文字を拒否する。`base`は`data/01_original_train/<model>/`配下に解決されたことを読込み前に確認し、manifestは型番、親子の元画像名、元画像名・分割画像名のmanifest内一意性、分割IDの親元画像内一意性を後続処理前に検証する。切り出し範囲は `[x,x+SIZE) × [y,y+SIZE)`、IDは0〜99で一意、比率合計1。設定書込みは一時ファイルから原子的置換する。
- **影響**: `config.py`、`paths.py`、設定フィクスチャ。

### 判断 3: SuperSimpleNet と依存関係

- **状態**: 確定
- **採用内容**: Python 3.13、Anomalib 2.6.2、PyTorch 2.13.0、torchvision 0.28.0、CUDA 13.0、SuperSimpleNet、`wide_resnet50_2.tv_in1k` を初期構成とし、uv のプラットフォーム別 source と lockfile で固定する。画像処理は OpenCV headless、探索は Optuna SQLite を用いる。
- **根拠**: 入力要件と公式配布情報が一致し、Anomalib 2.6.2 が SuperSimpleNet を提供するため。
- **代替案**: 独自モデル実装は保守範囲が広がるため不採用。GUI版OpenCVは画面を使わずOS依存を増やすため不採用。
- **実装規則 / 不変条件**: Linux/Windowsはcu130 wheel、GPU不能時は同じコードでCPUへ切替。依存版はrun metadataへ保存する。SuperSimpleNetは`post_processor=False`、`evaluator=False`、`visualizer=False`で構成し、決定的前処理とヒートマップ生成はアプリ側で一貫して管理する。
- **影響**: `pyproject.toml`、`uv.lock`、実機セットアップ記録。

### 判断 4: 元画像単位の分離

- **状態**: 確定
- **採用内容**: manifest の `source_image` をグループキーに、seed付きで80/20に分離し、両集合を空にしない。分割単位のランダム分離は禁止する。
- **根拠**: 同じ元画像の類似分割が学習・検証へ混在する情報漏洩を防ぐため。
- **代替案**: 分割画像単位の分離は要件違反のため不採用。
- **実装規則 / 不変条件**: 同一元画像の全成功分割は必ず同じ集合。両集合を作れなければ学習開始前エラー。
- **影響**: `training.py` と学習フィクスチャ。

### 判断 5: 正常画像のみの Optuna 目的関数

- **状態**: 確定
- **採用内容**: SuperSimpleNetのadaptor/segmentation-detection学習率比を維持する`0.25`〜`4.0`の学習率倍率、バッチサイズ`[4,8,16]`、エポック数`[200,300,400]`、特徴抽出層`[["layer2"],["layer2","layer3"],["layer3"]]`、前処理画像サイズ`[256,384,500]`を探索し、検証集合のPostProcessor適用前`pred_score`全体の99パーセンタイルを最小化する。ImageNet正規化・bilinear・antialiasは固定し、データ拡張条件と閾値は初期探索対象に含めない。
- **根拠**: 正解ラベルがない初期評価で再現可能な暫定指標を得るため。入力資料末尾の明示的な初期範囲を優先する。
- **代替案**: 学習損失のみ、分割ごとの平均、異常検出指標としての表示は目的と契約に合わないため不採用。
- **実装規則 / 不変条件**: seed 42のTPESamplerと、最初の5試行および50 epochをwarmupとして10 epoch間隔で判定するMedianPrunerを使う。枝刈り・失敗を含む合計50試行の条件・値・状態をstudyへ保存し、正常完了試行だけから最小値を選ぶ。study保存先は型番から`optuna/<model>/study.db`へ固定し、型番設定から任意パスを受け取らない。指標は性能値と表示しない。
- **影響**: `training.py`、`modeling.py`、結果表示。

### 判断 6: データ拡張境界

- **状態**: 確定
- **採用内容**: 学習データ量から自動判定せず、型番設定の`augmentation.enabled`で有効化し、順序、適用確率、範囲、seedを固定した変換パイプラインを学習 dataset の読込み時だけ適用する。検証・試験 pipeline は決定的前処理だけにする。初期値は平行移動±2%/確率0.5、回転±3度/0.5、明るさ・コントラスト係数0.9〜1.1/各0.3、色温度6500K±500K/0.2、ガンマ係数0.9〜1.1/0.3、Gaussianノイズ標準偏差0〜0.01/0.3、Gaussian blur kernel 3または5・sigma 0.1〜1.0/0.2とする。
- **根拠**: 元画像不変、非永続化、検証値の比較可能性を同時に満たすため。
- **代替案**: 拡張画像の事前生成は保存禁止に反するため不採用。初期Optuna探索対象化も範囲外。
- **実装規則 / 不変条件**: 変換は設定順に独立確率で適用し、連続値は一様分布から選ぶ。幾何変換の余白はreflection、色温度は1000K〜40000Kに制限した黒体色近似による6500K比、画素値は0〜1へ制限する。ぼかしカーネルは正の奇数とし、seedを記録する。
- **影響**: `modeling.py` のデータ境界、設定検証、テスト。

### 判断 7: ステージング、再開、明示的再生成

- **状態**: 確定
- **採用内容**: 画像準備と結果生成は同一ファイルシステム上の一時ディレクトリで完了後に置換する。学習はOptuna studyを通常再開し、`--restart` のみ対象型番の派生成果物を削除する。
- **根拠**: 中途半端な一式を後続処理が利用することと、誤った広範囲削除を防ぐため。
- **代替案**: 出力先への逐次上書きは失敗時の一貫性がないため不採用。
- **実装規則 / 不変条件**: 削除対象は解決済みの型番ディレクトリまたは単一checkpointに限定し、元画像・設定・pretrainedを削除しない。checkpoint、型番設定、最良試行結果は全件を別ファイルへステージングし、既存ファイルのバックアップとトランザクション記録を作成してから置換する。置換失敗時は即時、プロセス中断時は次の`train`または`test`開始前に旧一式へ復旧する。正常完了時はトランザクション記録を先に削除し、残ったバックアップは後処理として削除する。
- **影響**: preparation、training、evaluation、paths。

### 判断 8: GPU優先・CPUフォールバック

- **状態**: 確定
- **採用内容**: CUDA利用可否を実行時に判定し、利用可能ならCUDA、不能ならCPUを選ぶ。選択・切替理由・デバイス名をrun metadataへ保存する。
- **根拠**: 同じコマンドを両経路で動かし、結果の由来を追跡するため。
- **代替案**: GPU必須は要件違反。例外時だけ暗黙フォールバックする案は記録不足のため不採用。
- **実装規則 / 不変条件**: 明示的なデバイス選択結果をモデル生成前に確定し、CUDA初期化失敗時も一度だけCPUへ切替える。
- **影響**: `runtime.py`、modeling adapter、ログ。

### 判断 9: 判定優先順位

- **状態**: 確定
- **採用内容**: PostProcessor適用前`pred_score`が閾値以上なら `anomaly`。元画像集約は `anomaly` > `undetermined/error` > `normal` の優先順位とする。
- **根拠**: 異常の見逃しを避けつつ、全分割が判定できない画像を正常と誤表示しないため。
- **代替案**: エラーを無視して正常とする案、未判定を異常とする案はいずれも評価者の判断材料を歪めるため不採用。
- **実装規則 / 不変条件**: `normal` は必要な全分割が揃い全て閾値未満の場合だけ。判定不能スコアはnull。
- **影響**: `results.py`、JSON契約、評価テスト。

### 判断 10: スコアと暫定閾値の一貫性

- **状態**: 確定
- **採用内容**: 学習条件探索、暫定閾値算出および試験判定の全てで、SuperSimpleNetがsigmoid適用後に返すPostProcessor適用前`pred_score`を使用する。この値は0〜1だが校正済み確率とは扱わない。最良モデルをevalモード、データ拡張なし、同じ決定的前処理で学習集合へ再推論し、その99パーセンタイルを暫定閾値とする。
- **根拠**: AnomalibのPostProcessorによる正規化・適応閾値と独自の正常画像パーセンタイル閾値を混在させず、学習・閾値決定・試験で比較可能な同一スコア尺度を維持するため。
- **代替案**: Anomalibの適応F1閾値は異常ラベルを必要とし、正常画像中心の初期段階に合わない。PostProcessor正規化後スコアと独自閾値の併用は尺度の対応が不明確になるため不採用。
- **実装規則 / 不変条件**: `post_processor=False`とし、型番設定内でも`score.source == threshold.score_source`かつPostProcessor無効を検証する。`ScoreContract.source`は`supersimplenet.pred_score`、`anomalib_post_processor`はfalseのLiteralとし、検査結果の`runtime`は必須の`RunMetadata`として検証する。checkpoint、`best_trial.json`、型番設定、検査結果にスコア源とPostProcessor状態を保存し、不一致時は学習または推論開始前にエラーとする。試験推論はモデルの`pre_processor.transform`を直接使用し、探索・閾値算出と同じbilinear・antialias・ImageNet正規化を保証する。ヒートマップは同じ推論のPostProcessor適用前`anomaly_map`を使用する。
- **影響**: `modeling.py`、`training.py`、`evaluation.py`、成果物契約、学習・評価テスト。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 型番が不正・設定なし | config/paths | 書込みなし | 項目と期待形式、exit 2 | error log | 設定・型番を修正して再実行 |
| `base`が絶対パス・パス要素・ルート外参照 | config/paths | 読書きなし | `base`の期待形式、exit 2 | error log | 型番別学習元画像ルート内のファイル名へ修正 |
| 基準画像なし・読込不能 | preparation | 書込みなし | 対象パス、exit 2/3 | error log | ファイルを配置・修復 |
| ORB対応点不足・homography失敗・インライア比率不足 | imaging | 学習は元画像全除外、試験は未判定引継ぎ | 原因別の警告と対象画像 | manifest、警告件数 | 撮り直しまたは設定調整 |
| crop範囲外 | preparation | ステージング破棄、現行一式維持 | 元画像・split ID、exit 3 | error log | 範囲または位置合わせを修正 |
| 学習・試験元画像の読込み不能 | preparation/imaging | ステージング破棄、現行一式維持 | 元画像、exit 3 | error log | 画像形式・破損・権限を修正 |
| ブラックリストが未知画像/IDを参照 | config/preparation | 処理開始前に拒否 | 参照不整合、exit 2 | error log | 設定修正 |
| train/validation片方が空 | training | 学習開始なし | 必要数と現在数、exit 2 | error log | 元画像追加または比率変更 |
| 1試行の学習失敗 | training | 試行をfailedとしてstudy保持 | 試行番号と理由 | study、error log | 原因修正後通常再開 |
| 全試行失敗 | training | checkpoint/threshold更新なし | exit 3、既存成果物維持 | study、run metadata | 原因修正後再開/明示restart |
| 学習成果物一式の更新失敗・中断 | training | 即時または次回開始前にバックアップから旧一式を復旧 | exit 3、旧一式維持 | transaction記録、error log | 原因修正後通常再実行 |
| pretrained取得失敗 | modeling | 学習中止、既存キャッシュ不変 | 依存先失敗、exit 3 | error log | 通信確認またはキャッシュ配置 |
| checkpointと型番不一致 | evaluation | 推論開始なし | 期待/実際の型番、exit 2 | error log | 正しいモデルを指定 |
| スコア契約またはthresholdの欠落・不一致 | evaluation | 推論開始なし | 期待値と実値、不足項目、exit 2 | error log | 学習完了または設定同期 |
| 分割推論失敗 | evaluation/results | 分割error、元画像undetermined（他分割anomalyならanomaly） | JSONを保存し継続 | JSON、warning/error | 原因修正後再検査 |
| 結果JSON書込み失敗 | results | ステージング破棄、現行結果維持 | exit 3 | error log | 容量・権限確認後再実行 |
| 同じstem・異拡張子の試験元画像 | evaluation/results | 拡張子付き入力名を含む一意名で両方保存 | 各元画像のJSON・結果画像 | manifest、結果JSON | 不要 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力安全性 | 型番を安全な文字へ制限し、`base`をファイル名だけに制限して既知ルート配下へresolveする。JSON/INIは型検証し、checkpointはこのアプリが生成した型番メタデータ付き成果物だけを受け入れる | 絶対パス・パストラバーサル・ルート外参照・不正設定・型番不一致の自動テストが成功する |
| 秘密情報 | 画像内容、環境変数、絶対ユーザーパスを通常ログへ出さず、ファイル名と相対パス、必要な環境版だけを記録する | リポジトリ検査とログフィクスチャで秘密情報・画像バイトがないことを確認する |
| 再現性 | lockfile、seed、探索条件、dataset manifest、依存版、device、checkpoint、スコア契約、閾値対応を保存する | `best_trial.json`、検査結果の型付きruntime、スモーク結果の必須項目を自動で読み戻せる |
| 性能 | 各コマンドの処理時間を記録する。画像単位の処理時間と数値上限は初期評価要件に含めない | 実機スモーク記録にコマンド単位のdurationが存在し、評価者が後続目標を決定できる |
| GPU運用 | CUDA 13.0最低ドライバ以上を前提とし、採用版は実機試験後に記録する。GPU不能時はCPUへ切替える | Ubuntu/WindowsそれぞれGPU・CPUスモーク結果を保存する |
| 障害復旧 | 原子的置換、Optuna再開、対象限定restart、元画像不変を採用する | 中断・I/O失敗・restartテストで既存一式と非対象データが保持される |

## 移行とロールバック

1. 既存の正式仕様・業務データ・公開APIはなく、データ移行は不要である。
2. 導入時は依存関係とCLIを追加し、サンプル設定で自動試験後、対象OS実機へ同じlockfileを導入する。実データは運用者が `config/` と `data/01_original_train` / `data/02_original_test` へ配置する。
3. ロールバック時はCLIと追加依存を前版へ戻す。派生成果物は退避後に型番単位で削除できるが、元画像、型番設定、pretrainedキャッシュは自動削除しない。
4. 本番利用への移行はこのchangeに含めず、評価者が数値基準と承認条件を決定した後の別changeで扱う。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-001 | REQ-001-S01 | integration | コメントなしの正の整数 `SIZE` を含む有効設定でcheck | ID付き矩形画像と処理情報 | `tests/test_preparation.py::test_check_writes_labeled_ranges` | はい |
| TC-002 | REQ-001 | REQ-001-S02 | unit/integration | 範囲外・重複ID・非整数または非正の `SIZE` でcheck | exit 2、不完全出力なし | `tests/test_config.py::test_check_rejects_invalid_ranges` | はい |
| TC-003 | REQ-002 | REQ-002-S01 | integration | 位置合わせ可能な学習画像でtrain-pre | 命名契約どおり全分割保存、元画像不変 | `tests/test_preparation.py::test_train_pre_aligns_and_crops_images` | はい |
| TC-004 | REQ-002 | REQ-002-S02 | integration | blacklist一致でtrain-pre | 対象分割なし、除外記録あり | `tests/test_preparation.py::test_train_pre_excludes_blacklist_entries` | はい |
| TC-005 | REQ-002 | REQ-002-S03 | integration | 最低マッチ数、ホモグラフィ推定、最低インライア比率の各失敗をパラメータ化してtrain-pre | 元画像全分割除外と具体的理由の警告 | `tests/test_preparation.py::test_train_pre_warns_and_skips_alignment_failure` | はい |
| TC-006 | REQ-002 | REQ-002-S04 | integration | 位置合わせ後にcrop範囲外 | exit 3、現行一式維持 | `tests/test_preparation.py::test_train_pre_rejects_out_of_bounds_crop_atomically` | はい |
| TC-007 | REQ-003 | REQ-003-S01 | integration | blacklist一致を含む試験画像でtest-pre | 全分割を命名契約どおり保存 | `tests/test_preparation.py::test_test_pre_does_not_apply_blacklist` | はい |
| TC-008 | REQ-003 | REQ-003-S02 | integration | 最低マッチ数、ホモグラフィ推定、最低インライア比率の各失敗をパラメータ化してtest-pre | 未判定manifestと具体的理由の警告 | `tests/test_preparation.py::test_test_pre_carries_alignment_failure` | はい |
| TC-009 | REQ-003 | REQ-003-S03 | integration | 試験crop範囲外 | exit 3、正常入力扱いなし | `tests/test_preparation.py::test_test_pre_rejects_out_of_bounds_crop` | はい |
| TC-010 | REQ-004 | REQ-004-S01 | unit | 複数元画像、80/20、seed42で分離 | 再現可能かつグループ非混在 | `tests/test_training.py::test_split_groups_by_source_image` | はい |
| TC-011 | REQ-004 | REQ-004-S02 | unit | 両集合を作れない元画像数 | 学習前エラーに現在数を含む | `tests/test_training.py::test_split_rejects_insufficient_source_images` | はい |
| TC-012 | REQ-005 | REQ-005-S01 | integration | 規定探索空間、TPE/MedianPruner、PostProcessor無効`pred_score`で50試行をテストダブル実行 | 完了・枝刈り・失敗を含む全条件・状態・p99を記録し、正常完了試行の最小値を選択 | `tests/test_training.py::test_search_selects_lowest_validation_percentile` | はい |
| TC-013 | REQ-005 | REQ-005-S02 | unit | 正常画像のみの探索結果表示 | 暫定指標と表示し性能指標を称さない | `tests/test_training.py::test_search_report_labels_objective_as_provisional` | はい |
| TC-014 | REQ-006 | REQ-006-S01 | unit/integration | 規定の順序・確率・範囲・seedで各拡張設定を使い学習入力読込み | 決定的な設定変換適用、範囲・画素値制約、元・準備画像不変、非永続 | `tests/test_training.py::test_augmentation_is_training_only_and_ephemeral` | はい |
| TC-015 | REQ-006 | REQ-006-S02 | unit | 拡張有効設定で検証入力読込み | 拡張なしのスコア入力 | `tests/test_training.py::test_validation_pipeline_disables_augmentation` | はい |
| TC-016 | REQ-007 | REQ-007-S01 | integration | 最良試行完了後、eval・拡張なしで学習集合へ再推論 | checkpoint、best trial、型番設定へ同一スコア契約と`pred_score` p99 threshold保存 | `tests/test_training.py::test_training_persists_best_model_and_threshold` | はい |
| TC-017 | REQ-007 | REQ-007-S02 | integration | cache有/無で学習開始 | cache再利用、無い時だけ取得 | `tests/test_training.py::test_pretrained_weights_are_cached` | はい |
| TC-018 | REQ-008 | REQ-008-S01 | integration | 一部完了studyで通常train | 完了試行保持、残試行から再開 | `tests/test_training.py::test_training_resumes_existing_study` | はい |
| TC-019 | REQ-008 | REQ-008-S02 | integration | 旧成果物ありでtrain --restart | study/modelのみ置換、入力・設定・cache保持 | `tests/test_training.py::test_training_restart_replaces_only_derived_artifacts` | はい |
| TC-020 | REQ-009 | REQ-009-S01 | unit | CUDA利用可能を模擬 | CUDA選択とdevice記録 | `tests/test_runtime.py::test_select_device_prefers_available_cuda` | はい |
| TC-021 | REQ-009 | REQ-009-S02 | unit | CUDA不能を模擬 | CPU選択と理由記録 | `tests/test_runtime.py::test_select_device_falls_back_to_cpu` | はい |
| TC-022 | REQ-010 | REQ-010-S01 | integration | 同一スコア契約でPostProcessor無効`pred_score < threshold`としてtest | normal、`pred_score`、未変更結果画像 | `tests/test_evaluation.py::test_evaluation_records_normal_split` | はい |
| TC-023 | REQ-010 | REQ-010-S02 | integration | 同一スコア契約でPostProcessor無効`pred_score >= threshold`としてtest | anomaly、`pred_score`、PostProcessor適用前`anomaly_map`ヒートマップ | `tests/test_evaluation.py::test_evaluation_visualizes_anomalous_split` | はい |
| TC-024 | REQ-011 | REQ-011-S01 | unit | 一つ以上anomaly | overall anomaly | `tests/test_results.py::test_aggregate_prefers_anomaly` | はい |
| TC-025 | REQ-011 | REQ-011-S02 | unit | 必要分割が全てnormal | overall normal | `tests/test_results.py::test_aggregate_accepts_only_all_normal` | はい |
| TC-026 | REQ-011 | REQ-011-S03 | unit | anomalyなし、undetermined/errorあり | overall undetermined、再撮影案内 | `tests/test_results.py::test_aggregate_marks_incomplete_result_undetermined` | はい |
| TC-027 | REQ-012 | REQ-012-S01 | integration | 各終了状態の元画像結果確定 | スコア源・PostProcessor状態を含む必須JSON、enum、null score、UTC日時 | `tests/test_results.py::test_result_json_contains_traceable_contract` | はい |
| TC-028 | REQ-013 | REQ-013-S01 | integration | 旧結果ありでtest --restart | 結果のみ置換し他データ保持 | `tests/test_evaluation.py::test_evaluation_restart_replaces_only_results` | はい |
| TC-029 | NREQ-001 | NREQ-001-S01 | integration/e2e | 対象OSの固定環境で全CLIスモーク | 終了状態・時間・版・device記録、成果物読戻し | `tests/test_platform_smoke.py::test_workflow_records_runtime_contract` | はい（実機実行併用） |
| TC-030 | NREQ-001 | NREQ-001-S02 | integration/e2e | GPU無効でtrain/testスモーク | CPU完了、理由・時間記録 | `tests/test_platform_smoke.py::test_workflow_completes_with_cpu_fallback` | はい（実機実行併用） |
| TC-031 | REQ-001 | REQ-001-S03 | unit/integration | `base`へ絶対パス、`.`、`..`、パス区切り文字またはルート外参照を指定して設定読込み・check | 処理開始前にexit 2、既知ルート外を読書きしない | `tests/test_config.py::test_base_rejects_paths_outside_model_root` | はい |
| TC-032 | REQ-012 | REQ-012-S02 | unit/integration | スコア源、PostProcessor、判定enum、runtime必須項目または日時を不正にして結果生成・読戻し | 項目を特定して契約拒否、不正結果を正常扱いしない | `tests/test_results.py::test_result_contract_rejects_invalid_score_and_runtime` | はい |
| TC-033 | REQ-010 | REQ-010-S03 | unit/integration | モデル生成時のPreProcessorを保持した試験predictorへ非正方形画像を入力 | モデルと同一transformが1回適用され、独自resize・正規化を併用しない | `tests/test_evaluation.py::test_predictor_uses_model_preprocessor` | はい |
| TC-034 | REQ-012 | REQ-012-S03 | integration | 同じstemのPNG/JPEGを含むmanifestでtest | 拡張子付きのJSON・結果画像が全て共存し上書きなし | `tests/test_evaluation.py::test_evaluation_keeps_same_stem_different_extensions` | はい |
| TC-035 | REQ-002 | REQ-002-S04 | integration | 学習・試験準備でcrop範囲外 | エラーに元画像名・分割ID、現行一式維持 | `tests/test_preparation.py::test_crop_error_identifies_source_and_split` | はい |
| TC-036 | REQ-002 | REQ-002-S05 | integration | 読込み不能な学習元画像で準備CLI | exit 3、元画像名、現行一式維持 | `tests/test_runtime.py::test_preparation_image_io_failure_is_processing_error` | はい |
| TC-037 | REQ-007 | REQ-007-S03 | integration | checkpoint・設定・最良結果の置換途中失敗または未完了transactionあり | 即時または次回開始前に旧3成果物を復旧 | `tests/test_training.py::test_training_artifact_transaction_restores_previous_set` | はい |
| TC-038 | REQ-002 | REQ-002-S03 | unit/integration | train-pre/test-preの位置合わせ失敗 | 警告に元画像名・理由・再確認または再撮影案内 | `tests/test_preparation.py::test_alignment_warning_identifies_source_reason_and_action` | はい |
| TC-039 | REQ-003 | REQ-003-S04 | integration | 読込み不能な試験元画像で準備CLI | exit 3、元画像名、現行一式維持 | `tests/test_runtime.py::test_preparation_image_io_failure_is_processing_error` | はい |
| TC-040 | REQ-004 | REQ-004-S03 | unit/integration | 型番不一致、パス要素、重複元画像・分割画像、親子元画像名不一致または重複分割IDのmanifestを学習・検査へ入力 | 項目を特定して処理前拒否、既知ルート外不変 | `tests/test_results.py::test_manifest_contract_rejects_unsafe_or_inconsistent_entries` | はい |
| TC-041 | REQ-007 | REQ-007-S04 | unit/integration | 型番・checkpoint・閾値不一致または探索条件不正のbest_trialでtest | モデル生成前に項目を特定して拒否 | `tests/test_evaluation.py::test_evaluation_rejects_invalid_best_trial_contract` | はい |
| TC-042 | REQ-012 | REQ-012-S04 | unit/integration | 型番不一致、パス要素、重複元画像・分割画像、親子元画像名不一致または重複分割IDのmanifestを検査へ入力 | 項目を特定して推論前拒否、既知ルート外不変 | `tests/test_results.py::test_manifest_contract_rejects_unsafe_or_inconsistent_entries` | はい |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-001 | 3 | 3 | なし | 網羅 |
| REQ-002 | 5 | 7 | なし | 網羅 |
| REQ-003 | 4 | 4 | なし | 網羅 |
| REQ-004 | 3 | 3 | なし | 網羅 |
| REQ-005 | 2 | 2 | なし | 網羅 |
| REQ-006 | 2 | 2 | なし | 網羅 |
| REQ-007 | 4 | 4 | なし | 網羅 |
| REQ-008 | 2 | 2 | なし | 網羅 |
| REQ-009 | 2 | 2 | なし | 網羅 |
| REQ-010 | 3 | 3 | なし | 網羅 |
| REQ-011 | 3 | 3 | なし | 網羅 |
| REQ-012 | 4 | 4 | なし | 網羅 |
| REQ-013 | 1 | 1 | なし | 網羅 |
| NREQ-001 | 2 | 2 | なし | 網羅 |

## 未決事項

| 質問 | 回答期限 / 必要な工程 | 決定者 | 影響・未回答時の扱い |
| --- | --- | --- | --- |
| 本番利用に必要な検出性能、誤検出、処理時間の数値と承認条件は何か | 初期評価完了後・本番利用changeのproposal確定前 | 評価者 | 初期評価用の実装・試験は進める。本番利用へ移行しない |
| CUDA 13.0最低要件以上のどの安定版NVIDIAドライバを各OSで固定するか | 対象実機スモーク試験後・運用受け入れ前 | 運用者 | 最低版を下限として試験し、採用版未記録の環境を運用開始しない |
| 明示的再生成前に旧成果物を退避する運用を採用するか | 運用手順承認前 | 運用者 | 実装既定は対象派生成果物の削除・再生成とし、必要なら利用者が事前退避する |
