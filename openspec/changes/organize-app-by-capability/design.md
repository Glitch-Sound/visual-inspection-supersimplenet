## 背景・前提

`src/app/` は空の `__init__.py` と12モジュール、約2,600行からなる。`pyproject.toml` の5つの console script はすべて `app.cli` を参照する。`cli.py` は共通実行処理と5コマンドの組立てを兼ね、`modeling.py` は学習時拡張・共通モデル生成・評価用 predictor を兼ねる。`training.py` は探索・実学習・成果物の一式更新を兼ねる。既存のテストと `scripts/run_visual_inspection_smoke.py` は `app.*` を直接 import し、一部は文字列による monkeypatch を使用する。

正式仕様は `visual-inspection/image-preparation`、`model-training`、`model-evaluation` の3能力に分かれる。今回それらの観測可能な契約は変えないため、差分 spec は `skip_specs: true` として省略した。以下の AC-ID は今回の受け入れ条件であり、既存の REQ-ID は変更せず回帰確認の対象とする。

## 目標・対象外

### 目標

- 3能力と共通基盤の4領域に実行時コードを配置し、仕様から実装への対応を文書化する。
- 能力パッケージ間の直接 import をなくし、共有データ契約と実行基盤を `common/` に置く。
- CLI、設定、永続成果物、エラー、再実行の契約を既存テストと対象環境で確認する。

### 対象外

- 計算手順・学習条件・閾値・判定規則・ファイル契約の変更。
- 外部 Python 利用者向けの旧 `app.*` import パス維持。`pyproject.toml` が公開するのは console script であり、旧 import パスはアプリ内・同梱テスト・補助スクリプトの参照先として確認できる範囲で移す。別の外部利用が判明した場合は実装前に影響を再評価する。
- 依存関係更新、無関係なコード整理、新規の汎用ユーティリティ層。

## 要件トレーサビリティ

差分 spec はない。既存仕様と proposal の受け入れ条件への対応を示す。

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 業務フローと責務、技術判断1 | 仕様と配置、依存方向 | 1.2, 2.1, 2.2, 2.3, 4.1 | TC-001 | 配置表と import 検査 |
| AC-002 | インターフェースと失敗時の結果 | 5 CLI と共通実行処理 | 1.3, 2.1, 2.2, 2.3, 3.1, 3.3, 4.2, 4.3 | TC-002, TC-006 | help・CLI 出力・終了コードの回帰テストと延期した実機確認 |
| AC-003 | データ契約と状態、境界条件と失敗モード | manifest、学習・評価成果物 | 1.2, 2.1, 2.2, 2.3, 3.2, 4.2, 4.4 | TC-003, TC-007 | 既存契約・失敗・再実行・評価前復旧テストと延期した実機確認 |
| AC-004 | 技術判断4、試験設計、受け入れ検証 | 品質検査と対象環境 | 1.1, 4.2, 4.5 | TC-004, TC-005 | 自動試験・品質検査・延期した実機記録 |

### 既存仕様への回帰対応

差分 spec はないため、上の表は proposal の AC-ID だけを追跡する。既存の `REQ-001`〜`REQ-003` は画像準備（2.1、3.2）、`REQ-004`〜`REQ-008` は学習（2.2、3.2）、`REQ-009`〜`REQ-013` と `NREQ-001` は評価・実行記録（2.3、3.2、4.3〜4.5）で維持し、TC-003・TC-007 と既存テスト一式、TC-005 の実機確認に対応させる。

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 共通契約・基盤 | 移動 | 設定、型番、成果物、実行情報 | 同じ型・検証・パス・実行記録 | 標準ライブラリと既存依存 | `common/` に確定。複数能力が現に利用するものだけ置く |
| 画像準備 | 移動 | 基準画像、学習・試験画像、設定 | 確認画像、分割画像、manifest | `common/` | `image_preparation/` に確定 |
| モデル学習 | 移動・責務分割 | 学習 manifest、設定 | study、checkpoint、最良試行結果、閾値 | `common/` | `model_training/` に確定 |
| モデル評価 | 移動・責務分割 | 試験 manifest、学習成果物 | 可視化画像、検査 JSON | `common/` | `model_evaluation/` に確定 |

### 確定した配置

```text
src/app/
├── __init__.py
├── common/
│   ├── __init__.py
│   ├── atomic.py
│   ├── artifact_transaction.py
│   ├── cli.py
│   ├── config.py
│   ├── contracts.py
│   ├── image_io.py
│   ├── model_adapter.py
│   ├── paths.py
│   └── runtime.py
├── image_preparation/
│   ├── __init__.py
│   ├── cli.py
│   ├── imaging.py
│   └── preparation.py
├── model_training/
│   ├── __init__.py
│   ├── artifacts.py
│   ├── augmentation.py
│   ├── cli.py
│   ├── search.py
│   └── trainer.py
└── model_evaluation/
    ├── __init__.py
    ├── cli.py
    ├── evaluation.py
    ├── predictor.py
    └── results.py
```

| 現行 | 移動先・内容 |
| --- | --- |
| `atomic.py`、`paths.py`、`runtime.py`、`contracts.py`、`config.py` | それぞれ `common/` の同名ファイル。設定・契約は今回細分化せず、既存検証を保つ |
| `cli.py` | `_run`・`ExitCode` を `common/cli.py`、`check`・`train-pre`・`test-pre` を `image_preparation/cli.py`、`train` を `model_training/cli.py`、`test` を `model_evaluation/cli.py` |
| `imaging.py` | `ImageArray`・`ImageReadError`・`read_image`・`write_image` を `common/image_io.py`、`AlignmentError`・ORB・crop・確認画像描画を `image_preparation/imaging.py` |
| `preparation.py` | `image_preparation/preparation.py`。位置合わせ失敗時の警告、ステージング、学習・試験準備を維持 |
| `modeling.py` | 両能力が使うモデル生成を `common/model_adapter.py`、学習時拡張を `model_training/augmentation.py`、予測スコア抽出と事前学習重みの `ensure_cached` を `model_training/trainer.py`、checkpoint メタデータ読込み・テンソル変換・予測型・predictor を `model_evaluation/predictor.py` |
| `training.py` | データ分離・探索条件・study・探索と `TrialRunner` を `model_training/search.py`、Anomalib 実学習と dataset リンク・枝刈りを `model_training/trainer.py`、実行結果の表示文生成を `model_training/cli.py`、journal 名・stage/backup パス・一時ファイル除去と `recover_artifact_transaction` を `common/artifact_transaction.py`、journal 書込み・stage 置換・checkpoint メタデータ付与・最良試行保存・一式更新の組立て・restart を `model_training/artifacts.py` |
| `evaluation.py`、`results.py` | `model_evaluation/` の同名ファイル。判定集約は `results.py` に保持 |

`common/model_adapter.py` は汎用ツールではなく、学習と評価の両方が使う同一 SuperSimpleNet 生成の実装である。`common/artifact_transaction.py` は両能力が使う学習成果物一式の復旧と、その復旧・保存で共用する既存 journal 名、stage・backup パス、後片付けを扱う。探索は `model_training/search.py`、journal の書込み、stage から成果物への置換、閾値算出・保存順序は `model_training/artifacts.py` に残す。`common/config.py` と `common/contracts.py` は型番固有項目を含むが、3能力にまたがる読み込み・検証・受け渡しの正本として一箇所に維持する。`utils.py` と汎用 `exceptions.py` は作らない。現行の `ValueError` / `FileNotFoundError` / その他例外による終了コード判定を `common/cli.py` に維持する。

### 処理フロー

1. 各能力の CLI は `common/cli.py` の実行処理を使用し、`common/config.py` と `common/paths.py` から型番設定と保存先を取得する。
2. 画像準備は `common/image_io.py` と専用の画像処理を使って確認画像・分割画像・manifest を生成する。
3. 学習は `common/artifact_transaction.py` で前回中断分を復旧してから、`common/contracts.py` の `PreparationManifest` を読み、学習専用処理を経て `BestTrialResult` と checkpoint を既存の原子的手順で保存する。
4. 評価は `common/artifact_transaction.py` で前回中断した学習成果物一式を復旧してから、`PreparationManifest`、`BestTrialResult`、checkpoint を既存の検証を通して読み、同じモデル生成・スコア契約で結果を作成する。能力間の実装モジュールを直接 import せず、永続成果物と `common/` の契約を介して引き渡す。

### データ契約と状態

変更なし。`PreparationManifest`、`BestTrialResult`、checkpoint メタデータ、`InspectionResult`、型番別設定、study、分割画像と結果画像のフィールド・検証規則・保存先・更新者・ライフサイクルを維持する。正本の型定義を `common/contracts.py` へ移す。学習成果物の journal 名・内容、stage・backup 名、復旧順序は `common/artifact_transaction.py` と `model_training/artifacts.py` の境界で同一に保つ。JSON/INI/SQLite/checkpoint の移行は行わない。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `check`、`train-pre`、`test-pre` | console script → 画像準備 CLI | 既存 `--model` | 既存画像・manifest と実行記録、exit 0 | 設定・入力不備 exit 2、処理失敗 exit 3、位置合わせ失敗の既存警告・未判定 | 既存の一式置換を維持 |
| `train` | console script → 学習 CLI | 既存 `--model`、`--restart` | 既存 study・checkpoint・最良試行結果、exit 0 | 入力不備 exit 2、学習・保存失敗 exit 3、旧一式復旧 | 通常再開・明示 restart の範囲を維持 |
| `test` | console script → 評価 CLI | 既存 `--model`、`--restart` | 既存検査結果・可視化、exit 0 | 成果物契約不備 exit 2、処理失敗 exit 3、分割失敗の既存未判定 | 明示 restart の範囲を維持 |

## 技術判断

### 判断1: 能力間の依存方向

- **状態**: 確定。
- **採用内容**: 各能力から `common/` への import は許可し、能力パッケージ間および `common/` から能力パッケージへの import を禁止する。
- **根拠**: manifest と checkpoint はファイルを介して引き渡す。評価前に学習成果物一式を復旧する既存処理は両能力が使用するため、共通の成果物操作に置けば他能力の実装を呼ばずに維持できる。
- **代替案**: 3能力間の直接 import は変更時の影響を増やす。すべてを `common/` に移すと責務境界が失われる。
- **実装規則 / 不変条件**: 循環 import を作らず、共有部は実際に複数能力が使用する処理・契約に限る。`train` と `test` は従来と同じタイミングで `recover_artifact_transaction` を呼び、復旧失敗時の例外と終了コードを維持する。
- **影響**: import とテストダブルの patch 先を更新する。

### 判断2: 共通モデル境界

- **状態**: 確定。
- **採用内容**: 両能力が呼ぶモデル生成だけを `common/model_adapter.py` に置き、学習側のスコア抽出と評価側の predictor は各能力に置く。raw score の永続契約は `common/contracts.py` に維持する。
- **根拠**: 両能力で同じ前処理・スコアを使う既存契約を保ちつつ、学習・評価固有の依存を分けられる。
- **代替案**: `modeling.py` を丸ごと共通化すると、片方だけが使う処理が共通基盤に残る。
- **実装規則 / 不変条件**: スコア源、PostProcessor 無効、前処理、checkpoint 読み込み方を変更しない。
- **影響**: 学習・評価の import と monkeypatch の参照先。

### 判断3: CLI と import の互換性

- **状態**: 確定。
- **採用内容**: `pyproject.toml` の entry point を各能力の CLI へ更新し、`app.cli` の内部 import は新しい参照先へ移す。旧モジュールの薄い転送ファイルは常設しない。
- **根拠**: 公開操作は5つの console script であり、転送ファイルを残すと新旧2つの配置を保守する必要がある。
- **代替案**: `app.cli` を転送層として残す案は、外部 Python import の利用が確認された場合に限り再検討する。
- **実装規則 / 不変条件**: CLI 名・引数・help・標準出力・終了コードを保つ。リポジトリ内の import と patch 先を全件更新する。
- **影響**: `pyproject.toml`、テスト、補助スクリプト。entry point メタデータを更新した環境で実行確認する。

### 判断4: 差分仕様を省略した change の対応検査

- **状態**: 確定。
- **採用内容**: `.openspec.yaml` の `skip_specs: true` を明示した change に限り、spec 要件・Scenario との照合に代えて proposal の AC-ID を基準にする。design の「要件トレーサビリティ」は AC-ID を1行ずつ、試験設計は TC-ID ごとに AC-ID・単一の pytest 関数参照を記し、tasks の参照番号と突き合わせる。Scenario ID はこの経路に限り「該当なし」を許す。
- **根拠**: 現行 `scripts/check_openspec_traceability.py` は spec の存在と REQ/Scenario ID を必須とするため、OpenSpec CLI が許可する `skip_specs` change を検査できない。`npm run check` も同スクリプトを実行する。
- **代替案**: 架空の差分要件を作ると振る舞いが変わったように見える。検査を丸ごと省くとタスク・試験・受け入れ証跡の漏れを検出できない。
- **実装規則 / 不変条件**: `skip_specs` がない change は従来の REQ/Scenario 検査を維持する。省略経路でも AC-ID の重複・欠落、trace 行とタスク番号・TC-ID の不整合、pytest 参照書式を検査する。実装段階では単一参照のテスト収集、完了段階では全タスク完了と既存 `check_acceptance` による状態・証跡検査を実施する。spec 不在を無条件に許さない。
- **影響**: `scripts/check_openspec_traceability.py` と専用テスト。現行検査がこの change に失敗するため、設計時点では AC-ID と TC-ID の対応を手動レビューし、実装時には検査対応を先行させてからコード移動を進める。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| import・entry point の移動漏れ | パッケージ・CLI 試験 | 起動前失敗、成果物なし | import error または起動失敗 | TC-001、TC-002、品質検査 | 参照先を更新して再検証 |
| patch 先の移動漏れ | pytest | 意図しない実ライブラリ呼出しの可能性 | テスト失敗 | TC-003 | 新しい使用箇所へ patch を移す |
| manifest・checkpoint 契約の破損 | 学習・評価の既存検証 | 既存成果物の維持 | 従来どおり exit 2 または 3 | 既存の契約・復旧テスト | 入力・成果物を修正して再実行 |
| 中断した学習成果物一式の復旧漏れ | `train`・`test` の CLI と共通トランザクション処理 | journal に従い checkpoint・設定・最良試行を復旧 | 従来どおり復旧後に処理継続、復旧不能なら exit 3 | 学習の既存復旧テストと TC-007 | journal・backup を確認して再実行 |
| OS・GPU 経路の未確認 | 受け入れ検証 | コード・成果物は変更しない | 実機条件を未検証として残す | AC-004 と TC-005 の証跡 | 対象環境でスモーク実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力安全性 | 型番・パス・成果物契約の既存検証を同じ責務で維持 | 既存の不正入力テストが成功 |
| 秘密情報 | 設定・ログ・テストデータの実値を移動時に変更・追加しない | リポジトリ検査とレビュー |
| 性能 | 処理方式を変更しない。新たな数値目標は設けない | 実機スモークの処理時間を記録し、明らかな退行を確認 |
| 運用 | CLI・保存先・restart と復旧手順を維持 | 自動試験と対象環境の実行記録を区別 |

## 移行とロールバック

1. 既存データの移行は不要。コードと `pyproject.toml` を一体で切り替え、開発環境の entry point メタデータを更新して5 CLIを確認する。
2. 切り替えに失敗した場合はコードと `pyproject.toml` を同一版へ戻し、entry point を再生成する。既存の設定・画像・study・checkpoint・結果 JSON は変更しない。
3. 外部 Python import の利用が実装前に判明した場合は、互換期間と移行方法を design に追記してから実施する。

## 試験設計

差分 spec の Scenario はない。以下の TC は AC と既存仕様の維持を確かめる回帰ケースである。各行の pytest 実装は1関数だけを参照し、既存テスト一式の実行は `npm run check` で別に確認する。TC-003 は事前に作成した成果物の読戻しを、TC-005 はデバイス選択の CPU 切替を確認する。5 CLI の連続実行と対象 OS の GPU/CPU 経路はタスク4.3〜4.5の実機記録で区別して確認する。

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | AC-001 | 該当なし | unit | `app` 内の import を列挙する | 能力間と `common` から能力への import がなく、4領域を特定できる | `tests/test_package_structure.py::test_capability_import_boundaries` | はい | Python import の静的境界 | なし | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| TC-002 | AC-002 | 該当なし | integration | 5 entry point の import と `--help` を実行する | 5つとも従来名・引数で起動する | `tests/test_package_structure.py::test_console_script_entry_points` | はい | 現行開発環境の CLI 登録 | 対象 OS・4.3 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| TC-003 | AC-003 | 該当なし | integration | テスト内で確認画像・manifest・checkpoint・最良試行・検査結果を作成し、成果物読戻し処理を呼ぶ | 既存の成果物形式を読み戻せる | `tests/test_platform_smoke.py::test_workflow_records_runtime_contract` | はい | 開発環境での成果物契約の読戻し。CLI の連続実行は含まない | 5 CLI の実行・対象 OS・GPU/CPU・4.4 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| TC-004 | AC-004 | 該当なし | unit | `skip_specs: true` と通常の change を検査する | 省略経路の AC・TC・タスク・証跡を工程別に確認し、通常経路の厳格さを維持する | `tests/test_check_openspec_traceability.py::test_skip_specs_change_checks_design_tasks_and_acceptance` | はい | 開発基盤の両経路 | なし | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| TC-005 | AC-004 | 該当なし | unit | GPU 利用不可とデバイス初期化失敗を選択処理へ渡す | どちらも理由付きで CPU を選択する | `tests/test_runtime.py::test_select_device_falls_back_to_cpu` | はい | 開発環境でのデバイス選択。学習・推論の実行は含まない | 両 OS の実機4経路・4.5 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| TC-006 | AC-002 | 該当なし | integration | 共通 CLI 実行処理へ成功・入力不備・処理失敗の action を渡す | 標準出力 JSON の項目、結果・警告・エラー、exit 0・2・3 が従来どおりである | `tests/test_runtime.py::test_run_preserves_exit_contract` | はい | 共通実行処理の3分岐。5 CLI の正常経路はタスク4.3 | 対象 OS・4.3 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| TC-007 | AC-003 | 該当なし | integration | 学習成果物の backup と中断 journal を作り、壊れた現行一式がある状態で `test` CLI を実行する | 設定・checkpoint・最良試行を復旧してから読み、従来の成功結果を返す | `tests/test_evaluation.py::test_test_cli_recovers_interrupted_training_artifacts` | はい | 評価 CLI の復旧順序と成果物一式。predictor・推論処理はテストダブル | 実ライブラリでの5 CLI 実行・対象 OS・4.4 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |

## 網羅性確認

変更する spec 要件・Scenario は0件。既存の3仕様の Scenario は `npm run check` に含まれる既存テスト一式で回帰確認し、TC-003 で成果物の読戻し、TC-005 で CPU 選択、TC-007 で評価前の学習成果物復旧を個別に確認する。AC-001〜AC-004 は TC-001〜TC-007 と、AC-002〜AC-004 に対応する未実施タスク4.3〜4.5に対応する。設計上のテスト例外はない。

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 仕様3能力と共通領域の配置・依存方向 | TC-001、配置案内のレビュー | なし | 検証済み | `README.md` |
| AC-002 | 5 CLI、引数、出力、終了コード | TC-002、TC-006、タスク4.3の5 CLI 実行記録 | Ubuntu / Windows の実機5 CLI・4.3 | 未検証 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| AC-003 | manifest、checkpoint、結果、異常・再実行 | TC-003、TC-007、既存契約・復旧試験、タスク4.4の成果物読戻し | Ubuntu / Windows の実機成果物・4.4 | 未検証 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |
| AC-004 | 自動試験・品質検査、Ubuntu / Windows の GPU / CPU | TC-004、TC-005、`npm run check`、タスク4.5で `train`・`test` の実際のデバイスを照合 | 実機4条件・4.5 | 未検証 | `openspec/changes/organize-app-by-capability/evidence/acceptance.md` |

AC-002〜AC-004 の「未検証」は、対象 OS の実機受け入れが未完了であることを示す。開発環境で成功した自動試験とレビューの範囲は証跡に残し、実機結果として扱わない。延期するAC-IDと未完了タスク番号、確認内容はリポジトリの `README.md` に記録する。制限付きアーカイブは運用開始の承認ではない。
