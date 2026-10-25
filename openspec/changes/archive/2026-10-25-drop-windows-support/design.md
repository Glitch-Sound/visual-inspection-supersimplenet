## 背景・前提

現行の `config.py` と `contracts.py` はファイル名の検証で POSIX パスに加えて Windows のドライブ名を判定する。<br />
`tests/test_package_structure.py` は Windows 用の実行ファイル接尾辞を分岐し、`pyproject.toml` は Linux と Windows の PyTorch を CUDA index から取得する。<br />
対象環境の正本はモデル評価仕様の `NREQ-001` に置き、画像準備仕様は基準画像名と準備試験の境界を扱う。<br />
現行 README の延期表には Windows 専用の未検証項目もある。これを検証済みへ読み替えず、対象外になった理由を記録する。

## 目標・対象外

### 目標

- POSIX のパス検証を維持し、Windows 固有のドライブ名検証と試験分岐を除去する。
- Ubuntu 24.04 LTS (ネイティブまたは WSL2) と Apple silicon の macOS に合う依存取得条件とロックファイルを揃える。
- 現行案内、正式仕様、進行中 change の対象環境と試験を揃え、未検証の受け入れ確認を正確に追跡する。

### 対象外

- 旧成果物の変換・互換試験、Windows の動作試験、Apple GPU 対応。指定された運用範囲に含まれない。
- アーカイブ済み change と証跡の書換え。過去の記録を保存する。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | 業務フローと責務、インターフェースと失敗時の結果 | 型番設定の検証、確認画像 | 1.1、1.2、3.1 | TC-001〜TC-005 | pytest と対象環境の `check`、保存結果の照合 |
| NREQ-001 | 業務フローと責務、技術判断、移行とロールバック | 依存導入、全 CLI、運用記録 | 2.1、2.2、3.2、3.3 | TC-006、TC-007 | pytest、対象環境ごとの全工程スモークと読戻し |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 型番設定の基準画像名検証 | 変更 | `base: str` | 受理または入力不備 | `ProjectPaths` | `src/app/common/config.py`、既存の検証箇所を変更 |
| 準備・結果のファイル名検証 | 変更 | ファイル名文字列 | 受理または入力不備 | manifest・結果契約 | `src/app/common/contracts.py`、既存の共通検証を変更 |
| CLI 登録試験 | 変更 | 5コマンド | 実行可否 | インストール済み配布物 | `tests/test_package_structure.py`、既存試験を変更 |
| 依存取得 | 変更 | OS、ロックファイル | 対象環境の固定済み依存 | uv、PyTorch index | `pyproject.toml` と `uv.lock`、取得条件を変更 |
| 受け入れ案内 | 変更 | 対象環境、延期条件 | 実施手順と未検証記録 | README、正式仕様、進行中 change | 現行文書を更新 |

### 処理フロー

1. 運用者が対象環境で依存関係を同期する。Linux では CUDA index、macOS では通常の解決経路を使用する。
2. 運用者が型番設定を渡す。検証器は空名、`.`、`..`、`/`、`\`、POSIX 絶対パスを拒否し、入力不備を返す。
3. 運用者が準備・学習・検査を順に再実行する。失敗時は理由を確認して該当工程から再実行し、旧成果物を互換性の根拠として使わない。
4. 運用者は既存テストと全工程スモークの結果を対象環境ごとに記録し、評価者は未検証条件を区別する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番設定・manifest・結果 JSON | 形式変更なし | 既存契約を維持 | POSIX 名検証を維持 | 既存 CLI | 旧成果物は引き継がず再生成 |
| `uv.lock` | 変更 | 依存版と対象マーカー | Windows 向け CUDA 取得条件を除去 | uv | 対象環境で同期し直す |
| 延期中の受け入れ確認 | 変更 | change、AC-ID、状態、確認内容 | 未実施は未検証 | 運用者 | Windows 専用確認は対象外の理由を記録 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 型番設定の検証 | 運用者 → 5 CLI | `base` | 安全な名前を受理 | POSIX 絶対パス・区切り文字・`.`・`..` → 入力不備、旧成果物は更新しない | 設定を修正して再実行 |
| 固定依存の導入 | 運用者 → uv | 対象 OS、ロックファイル | 同期完了 | 解決・取得失敗 → 導入中断、全工程を開始しない | 環境を確認して再実行 |
| 全工程スモーク | 運用者 → 5 CLI | 型番と画像 | 新成果物と実行記録 | 準備・学習・検査失敗 → 原因を記録し、該当工程から再実行 | 出力先を分けて再実行 |

## 技術判断

### 判断・候補: パス検証

- **状態**: 確定
- **採用内容**: `PureWindowsPath` によるドライブ名判定だけを削除する。
- **根拠**: 対象 OS は POSIX パスを使用する。既存の `/` と `\`、`.`、`..`、`Path.is_absolute()` による拒否は残せる。
- **代替案**: 検証器の全面置換は不要な変更範囲を広げるため採用しない。
- **実装規則 / 不変条件**: 設定と成果物名の両方でルート外参照を許さない。
- **影響**: `config.py`、`contracts.py` と対応する回帰試験。

### 判断・候補: 依存取得と対象環境

- **状態**: 確定
- **採用内容**: PyTorch と torchvision の CUDA index マーカーを `sys_platform == 'linux'` にし、uv の解決対象を Linux と Apple silicon macOS に限定して `uv lock` でロックを更新する。WSL2 は Linux として扱う。
- **根拠**: Ubuntu と WSL2 は Linux パッケージ経路を用いる。Apple silicon の macOS は既存の CPU 経路を用いる。
- **代替案**: Windows マーカーを残す案はサポート終了と矛盾するため採用しない。
- **実装規則 / 不変条件**: 関係のない依存版更新を加えない。CLI と JSON の形は変えない。
- **影響**: `pyproject.toml`、`uv.lock`、対象環境の同期と試験。

### 判断・候補: 過去の検証記録

- **状態**: 確定
- **採用内容**: README の延期表を新しい対象環境へ更新する。Windows 専用の未検証条件は履歴として明示して現行確認対象から外す。進行中 change は整合させ、アーカイブ済み文書は保持する。
- **根拠**: 未実施の確認を実施済みと誤認させず、過去の判断も保持する。
- **代替案**: 履歴の一括置換は当時の証跡を書き換えるため採用しない。
- **実装規則 / 不変条件**: AC-ID と未検証状態を改変しない。現在の対象環境と過去の記録を区別する。
- **影響**: README、正式仕様、進行中 change。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 絶対パス・親参照 | 設定・契約検証 | 成果物を更新しない | 入力不備 | CLI の標準エラーと実行記録 | 名前を修正して再実行 |
| 依存取得失敗 | uv | 導入未完了 | 同期失敗 | 実行環境とエラーを記録 | 対象環境と index を確認 |
| 全工程の途中失敗 | 各 CLI | 既存の公開規則に従う | 失敗工程と理由 | スモーク結果 | 準備・学習・検査を必要な順序で再実行 |
| macOS に CUDA がない | デバイス選択 | CPU を使用 | 使用デバイスを表示・記録 | 実行記録 | CPU で完了できるか確認 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | POSIX 絶対パス、区切り文字、親参照を拒否 | pytest と入力不備時の成果物不変 |
| 性能 | 本番数値基準は変更しない | スモーク記録の処理時間を確認し、既存の未決事項を維持 |
| 運用 | 対象環境別の自動試験と実画像スモークを分ける | OS、Python・依存版、デバイス、コマンド、結果、読戻しを証跡へ記録 |

## 移行とロールバック

1. 対象環境へ依存関係を同期し、旧成果物を利用しない状態で型番設定と画像を用意する。
2. `check`、`train-pre`、`train`、`test-pre`、`test` を順に実行し、新成果物を読み戻して完了を判断する。互換期間と変換処理は設けない。
3. ロールバックが必要なら変更前のコードとロックファイルへ戻し、その版で準備・学習・検査を再実行する。新旧成果物の混用はしない。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-001 | REQ-001-S01 | integration | 有効な型番設定で `check` | 全・グループ画像と実行結果 | `tests/test_preparation.py::test_group_req_001_s01` | はい | 固定画像と CLI 契約 | 対象環境の実画像、3.3 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| TC-002 | REQ-001 | REQ-001-S02 | integration | 無効な範囲で `check` | 入力不備、正常画像を保存しない | `tests/test_preparation.py::test_group_req_001_s02` | はい | 分割範囲の境界 | 対象環境の実画像、3.3 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| TC-003 | REQ-001 | REQ-001-S03 | integration | `base` に POSIX 絶対パス・親参照・区切り文字 | 理由を示して拒否、ルート外不変 | `tests/test_preparation.py::test_group_req_001_s03` | はい | 型番設定と既存契約の拒否 | 対象環境の CLI、3.3 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| TC-004 | REQ-001 | REQ-001-S04 | integration | 縮小倍率0.5と境界座標で `check` | 指定位置の矩形 | `tests/test_preparation.py::test_group_req_001_s04` | はい | 既存の座標契約 | 対象環境の実画像、3.3 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| TC-005 | REQ-001 | REQ-001-S05 | integration | 重複所属で `check` | 両グループの画像に同じ分割 | `tests/test_preparation.py::test_group_req_001_s05` | はい | 既存のグループ契約 | 対象環境の実画像、3.3 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| TC-006 | NREQ-001 | NREQ-001-S01 | integration / e2e | 固定依存を同期し全工程を実行 | 実行記録と新成果物の読戻し | `tests/test_platform_smoke.py::test_workflow_records_runtime_contract` | はい | テストダブルと保存契約、ローカル環境 | 対象環境の固定依存・実画像・全 CLI、3.3 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| TC-007 | NREQ-001 | NREQ-001-S02 | unit / e2e | CUDA を無効化して学習・検査 | CPU 選択と切替理由を記録 | `tests/test_platform_smoke.py::test_workflow_completes_with_cpu_fallback` | はい | 実行記録の契約 | 対象環境での実学習・検査、3.3 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |

`tests/test_preparation.py::test_group_req_001_s03` に POSIX 絶対パスと区切り文字を追加する。<br />
成果物名の共通検証は `tests/test_config.py::test_safe_artifact_filename_posix_path_rejected` を追加して確認する。

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-001 | 5 | 5 | なし | 設計済み |
| NREQ-001 | 2 | 2 | なし | 設計済み |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | Ubuntu 24.04 LTS (ネイティブまたは WSL2) と Apple silicon macOS、固定済み依存・既存テスト | 両環境で `uv sync --locked` と `npm run check`、環境・版・結果を記録 | 対象環境での実行、3.2 | 未検証 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| AC-002 | 両対象環境、CPU と利用可能な CUDA GPU、全工程と新成果物読戻し | 実画像のスモークを実行し、結果 JSON と生成物を確認 | 対象環境の全工程、3.3 | 未検証 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| AC-003 | 基準画像名と成果物名の通常値・POSIX 絶対パス・区切り文字・親参照 | TC-003 と共通契約の pytest、対象環境 CLI | テスト実装と対象環境確認、1.2・3.3 | 未検証 | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |
| AC-004 | README、正式仕様、進行中 change、延期表 | 対象環境、再実行方針、未検証状態をレビュー | なし | 検証済み | openspec/changes/archive/2026-10-25-drop-windows-support/evidence/acceptance.md |

## 試験例外

なし。文書の整合は AC-004 のレビューで確認し、実装変更を伴う Scenario は上記の pytest で検証する。
