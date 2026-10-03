# Python Template
`uv` と `OpenSpec` を使用した `Python` 開発用テンプレートです。


## 1. 開発環境
- `Python` 3.13
- `uv`
- `OpenSpec`


### 1.1. 対応 AI コーディングエージェント
- `OpenAI Codex`
- `Claude Code`
- `GitHub Copilot`


## 2. クイックスタート
依存関係をインストールします。

```bash
uv sync --locked
npm ci
```

### Dev Container（任意）

Docker で開発したい場合は、Docker Engine と Dev Containers に対応したエディターを用意し、このリポジトリをコンテナで再度開いてください。<br />
VS Code では Dev Containers 拡張機能の **Reopen in Container** を使用します。

コンテナには Python 3.13、`uv`、Node.js 22 が含まれ、作成時に `uv sync --locked` と `npm ci` が実行されます。<br />
`.venv`、`node_modules`、パッケージキャッシュは Docker ボリュームに分離されるため、ホストの依存関係やOS固有のバイナリとは混在しません。<br />
依存関係を変更した場合は、コンテナ内で通常どおり次を実行してください。<br />

```bash
uv sync --locked
npm ci
```

### OpenSpec 更新（任意）

OpenSpec を更新する場合は、先にプロジェクトローカルの CLI とロックファイルを更新してから、生成済みの agent 用 instructions を更新します。<br />
CLI を更新せずに `openspec update` だけを実行しても、新しいワークフローは導入されません。<br />
`.agents/` と `.claude/` の instruction は OpenSpec が対象エージェント向けに生成する成果物であり、手作業で片方だけを変更しません。<br />
生成差分をレビューしたうえで次を実行します。

```bash
npm install --save-dev @fission-ai/openspec@latest
npx --no-install openspec update
```

アプリケーションを実行します。

```bash
uv run python-template
```

### 2.1. 外観検査ワークフロー

対象型番ごとに、次の入力を配置します。`<model>` には英数字・`_`・`-`だけを使用できます。

```text
config/setting.ini                  # [IMAGE] SIZE（正の整数）
config/part_<model>.json            # 分割、位置合わせ、探索、拡張、閾値
data/01_original_train/<model>/     # 基準画像と正常な学習画像
data/02_original_test/<model>/      # 検査対象画像
```

初回は、確認画像を目視してから前処理、学習、検査の順に実行します。

```bash
uv run --locked check --model XX
uv run --locked train-pre --model XX
uv run --locked train --model XX
uv run --locked test-pre --model XX
uv run --locked test --model XX
```

主な成果物は次の場所へ保存されます。

| 成果物 | 保存先 |
| --- | --- |
| 分割位置の確認画像 | `data/03_check/<model>.png` |
| 学習・試験用分割画像とmanifest | `data/04_train/<model>/`、`data/05_test/<model>/` |
| Optuna studyと最良試行 | `optuna/<model>/study.db`、`best_trial.json` |
| 学習済みcheckpoint | `weights/<model>.ckpt` |
| 可視化画像と元画像単位のJSON結果 | `data/06_result/<model>/` |

`train` は既存のOptuna studyを再開します。探索とcheckpointを破棄して再生成する場合だけ `train --model XX --restart`、検査結果だけを再生成する場合は `test --model XX --restart` を使用します。元画像、型番設定、事前学習重みキャッシュは削除されません。

位置合わせはORB対応点20件以上、RANSAC再投影誤差3.0px、信頼確率0.995、返却マスクのインライア比率0.5以上を初期値とします。学習時の失敗画像は理由付きで除外し、試験時の失敗画像は正常とはせず`undetermined`として引き継ぎます。異常がなくても必要な分割が揃わない場合は`undetermined`となるため、結果JSONの案内に従って再撮影または評価者判断を行います。

初期探索はseed 42で50試行を行い、学習率倍率`0.25`〜`4.0`、batch size `4/8/16`、epoch `200/300/400`、特徴層`layer2`・`layer2+layer3`・`layer3`、画像サイズ`256/384/500`を対象とします。学習入力だけに、平行移動、回転、明るさ、コントラスト、色温度、ガンマ、センサーノイズ、Gaussian blurを`config/part_<model>.json`の順序・確率・範囲で適用し、拡張画像は保存しません。検証・試験には適用しません。

探索、暫定閾値、検査判定はすべてAnomalib PostProcessorを無効にした`supersimplenet.pred_score`を使用します。最良モデルで学習集合を再推論したスコアの99パーセンタイルを暫定閾値とし、checkpoint、`best_trial.json`、型番設定へ同じ値を保存します。この0〜1の値は校正済み確率ではなく、探索の目的値も本番の検出性能値ではありません。

探索・暫定閾値算出・検査は、モデルに設定された同じbilinear・antialias・ImageNet正規化の前処理を使用します。checkpoint、`best_trial.json`、型番設定の閾値は一式として更新され、更新の中断を検出した次回の`train`または`test`では旧一式へ復旧してから処理します。

検査結果JSONは`<拡張子付き元画像名>.json`、分割結果画像は`<拡張子付き分割画像名>_result.png`として保存します。例えば`sample.png`と`sample.jpg`が同じ型番に存在しても、互いの結果を上書きしません。画像読込み不能と準備中の分割範囲外は処理失敗`3`となり、既存の準備成果物は維持されます。位置合わせ失敗の警告には対象画像、理由、再確認または再撮影の案内が含まれます。

準備manifestは要求型番、パス要素を含まない画像名、元画像と分割画像の一意性、元画像と分割の対応、一意な分割IDを読込み時に検証します。`best_trial.json`も型付きで読み戻し、型番、checkpoint参照、スコア契約、閾値が一致しない場合はモデル生成前に終了します。

`--restart`は対象成果物を直ちに削除するため、旧成果物が必要な運用では実行前に任意の場所へ退避してください。ロールバック時はコードと依存関係を前版へ戻し、必要に応じて退避済み成果物を復元します。元画像、型番設定、`pretrained/`はロールバック時にも自動削除しません。

CUDAが利用可能な場合はGPUを優先し、利用不能または初期化失敗時はCPUへ切り替えます。各コマンドの標準出力と検査結果JSONには、OS、Python・依存版、デバイス、開始・終了時刻、処理時間、警告・エラー、終了コードが記録されます。終了コードは成功`0`、入力不備`2`、処理失敗`3`です。

Ubuntu 24.04 / Windows 11のGPU・CPU実機確認では、少量の評価用データを配置して次を実行し、生成されたJSONを試験証跡として保存します。本番利用の性能・誤検出基準はこの初期評価とは別に決定してください。

```bash
uv run --locked python scripts/run_visual_inspection_smoke.py \
  --model XX \
  --output smoke/visual-inspection-XX.json
```

## 3. 開発

コミット前には高速な基礎検査を実行します。<br />
初回だけフックを有効化してください。

```bash
uv run --locked pre-commit install
uv run --locked pre-commit run --all-files
```

統合前、または雛形の広範な変更後は、完全な品質検査を実行します。

```bash
npm run check
```

テストを実行します。

```bash
uv run --locked pytest
```

リントを実行します。

```bash
uv run --locked ruff check .
```

フォーマットを実行します。

```bash
uv run --locked ruff format .
```

型チェックを実行します。

```bash
uv run --locked pyright
```

コミット時には以下のチェックを実行します。

| チェック | 内容 |
| --- | --- |
| `Ruff lint` | `Python` コードを静的解析します。<br />バグ、インポート順、モダンな構文、簡略化、静的に検出できるセキュリティ上の問題を確認します。 |
| `Ruff format` | `Python` コードが `Ruff` のフォーマットに従っているか確認します。 |
| `Repository checks` | 1 MB を超えるファイル、マージ競合の痕跡、不正な `YAML`/`TOML`、秘密鍵、末尾改行・行末の空白を検出します。 |

コミットを速く保つため、型検査、全テスト、OpenSpec のトレーサビリティは `npm run check` にまとめています。

### 3.1. AI コーディングエージェントの指示

共通の開発方針は [AGENTS.md](AGENTS.md) を正本とし、OpenAI Codex、Claude Code、GitHub Copilot から参照します。<br />
GitHub Copilot はリポジトリ共通の [`.github/copilot-instructions.md`](.github/copilot-instructions.md) も読み込みます。雛形・文書・振る舞いを変えない保守は直接変更できます。一方、外部から観測できる振る舞い、API、データ、セキュリティ、性能、外部連携、移行・運用を変える作業は OpenSpec change を先に作成します。曖昧な場合は要件を作り出さず、利用者に確認してください。


## 4. SDD
各ユースケースでの開発の方法です。<br />
なお、ここでは `Codex` での手順を基準とします。

主に `openspec` 配下で管理され、以下構造となります。

```text
python-template/
└── openspec/
    ├── specs/            # 最新仕様
    ├── changes/          # 変更計画
    │
    ├── schemas/          # 成果物定義
    │
    ├── config.yaml       # 共通ルール
    ├── product.md        # プロダクト定義
    ├── tech.md           # 利用技術定義
    └── structure.md      # 構造定義
```


### 4.1. 初期設定
事前に以下プロダクト全体に関連する定義を行なってください。

| ファイル | 定義内容 |
| --- | --- |
| config.yaml | 追加ルール、適用・保存時の運用リストなど |
| product.md | 目的・スコープ・中核機能・ユースケース・ドメインなど |
| tech.md | アーキテクチャ・主要ライブラリ・開発基準・テストなど |
| structure.md | ディレクトリ構造・命名規則・配置原則など |


### 4.2. 開発の流れ
以下の順番で開発を進めてください。


#### 4.2.1. 調査・検討
どのように進めていくか、チャットベースで相談してください。
```text
$openspec-explore [テーマ]
```


#### 4.2.2. 作業ディレクトリ生成
`openspec/config.yaml` の `schema: my-workflow` を既定スキーマとして、`openspec/changes/変更名/` が生成されます。<br />
各 change の `.openspec.yaml` に使用スキーマが記録されるため、以後の成果物生成・実装・検証でも同じワークフローが使用されます。
```text
$openspec-new-change [変更名]
```


#### 4.2.3. 補足資料を用意（任意）
要件定義書、既存設計、調査結果などの補足資料がある場合は、`openspec/changes/変更名/input.md` に格納できます。<br />
`input.md` は OpenSpec が自動で読み込むファイルではないため、次の工程で「`input.md` を参照する」と明示して使用してください。

`input.md` は、実装案より先に、利用者と運用者が何を達成・判断するかを整理する資料として作成します。次の順序が推奨例です。

1. **目的と利用者**: 解決したい問題、結果を使う人、運用する人、外部システムとそれぞれの判断を記載します。
2. **現行・変更後の業務フロー**: 開始条件から完了までの操作、判断、引き継ぎを時系列で記載します。
3. **判定や処理結果の扱い**: 利用者が受け取る結果、保存・通知、次に可能な操作、後続業務への引き継ぎを記載します。
4. **例外時の運用**: 入力不備、処理失敗、未判定、再実行など、該当する事象の表示・状態・復旧・責任分界を記載します。
5. **品質目標と受け入れ条件**: 実際の運用で必要な精度、性能、可用性、安全性と、運用開始を判定する条件を記載します。
6. **データ・環境上の制約**: 利用可能なデータ、入出力形式、実行環境、外部連携、セキュリティや運用時間の制約を記載します。
7. **技術候補・参考資料**: 検討済みの方式、ディレクトリ構成例、設定例、既存設計、調査結果を、事実・制約・候補に分けて記載します。

案件に該当しない項目は、理由を示して省略できます。特に品質目標の数値、閾値、承認者、例外時の責任分界が未確認な場合は推測で埋めず、「未決」と影響する工程を明記します。技術候補、ディレクトリ構成例、設定例を含めても構いませんが、それらは design で根拠を確認する候補であり、未確認の業務要件または採用済みの実装方式として確定しません。


#### 4.2.4. ドキュメント生成
変更内容と、明示的に参照を依頼した `input.md` を基に、実装に必要なドキュメントを生成します。
```text
$openspec-ff-change [変更名] input.md を要件の入力資料として参照し、既存の仕様・コード・設定と照合して、実装開始に必要な成果物を生成してください。
矛盾や実装可否を左右する未決事項は推測せず明示してください。
```

通常の開発では、`openspec-ff-change` で proposal、specs、design、tasks を依存関係順に一括生成する方法を既定とします。<br />
一括生成は上流工程やレビューを省略するものではなく、成果物ごとの対話・待ち時間を減らすために使用します。

生成後は proposal → specs → design → tasks の順に内容をレビューします。<br />
上流の前提や要件を修正する場合は、`openspec-update-change` を使って下流の設計・タスクとの整合性も更新します。<br />
未解決の重要事項を残したまま実装へ進みません。

次のように変更の前提や影響が不明確な場合は、一括生成の前に `openspec-explore` で調査・検討します。

- 利用者、運用者、変更後の業務フロー、受け入れ条件が定まっていない。
- 外部 API、権限・セキュリティ、不可逆なデータ移行など、失敗時の影響が大きい。
- 技術候補によって実現できる要件・運用フローが大きく変わる、または既存仕様と `input.md` に矛盾がある。

生成される成果物では、次の対応関係を管理します。

| 成果物 | 記載する内容 |
| --- | --- |
| `proposal.md` | 目的、利用者・運用者、現行・変更後の業務フロー、対象・対象外、運用開始の受け入れ条件 |
| `spec.md` | 利用者または外部システムから観測できる要件とScenario、試験方針、要件に影響する未決事項 |
| `design.md` | 業務フローを満たす責務、データ契約、失敗時の結果、技術判断、Scenarioごとの試験ケースID (`TC-001`) と確定後のpytest実装先 |
| `tasks.md` | 確定した設計から展開した実施作業と完了条件、要件ID・Scenario ID・TC-IDとの対応 |

実装変更を伴う `Scenario` には、自動テストコードを作成します。<br />
文書のみの変更など、テストコードが不要な場合は、`design.md` の「試験例外」に理由、承認者、期限を記録します。

成果物の対応は、任意の時点で次のコマンドにより確認できます。<br />
これはコミットごとには実行せず、設計レビュー、実装前、verify / archive 前、統合前に実行してください。

```bash
# 指定した変更を確認
uv run --locked python scripts/check_openspec_traceability.py --change <change-name>

# 進行中の全変更を確認
uv run --locked python scripts/check_openspec_traceability.py --all
```

検査対象は、全REQ/NREQのScenario、設計書が参照する実在タスクとその要件ID、全ScenarioのTC-IDとpytest実装先、全TC-IDのpytestテスト作成・実行タスクです。


#### 4.2.5. ドキュメント改善
生成したドキュメントを壁打ちしながら品質を向上させます。
```text
$openspec-update-change [変更名] [修正内容]
```


#### 4.2.6. 実装
生成したドキュメントから実装を行います。
```text
$openspec-apply-change [変更名]
```


#### 4.2.7. 検証
実装内容が問題ないか検証します。
```text
$openspec-verify-change [変更名]
```


#### 4.2.8. 仕様反映
変更内容を正式仕様として反映します。
```text
$openspec-archive-change [変更名]
```

アーカイブ前には、OpenSpec の厳密検証とトレーサビリティ検査の両方を通します。
```bash
npx --no-install openspec validate <change-name> --strict
uv run --locked python scripts/check_openspec_traceability.py --change <change-name>
```


## 5. 事前設定
このテンプレートは以下のコマンドを用いて作成しています。


### 5.1. プロジェクトの作成
```bash
uv init python-template \
  --name python_template \
  --app \
  --python "==3.13"
```


### 5.2. アプリケーションの依存関係
アプリケーションの実行時に使用するパッケージです。

```bash
uv add typer loguru pydantic-settings rich
```

| パッケージ | 説明 |
| --- | --- |
| `typer` | 型ヒントを利用して `CLI` アプリケーションを構築するためのライブラリです。<br />コマンド、引数、オプション、ヘルプなどを簡潔に定義できます。 |
| `loguru` | `Python` 標準の `logging` よりシンプルな `API` でログ出力を扱うためのライブラリです。<br />ログレベル、ファイル出力、ローテーションなどを簡単に設定できます。 |
| `pydantic-settings` | 環境変数や `.env` などからアプリケーション設定を読み込み、`Pydantic` による型検証を行うためのライブラリです。 |
| `rich` | ターミナル出力を見やすく装飾するためのライブラリです。<br />色付きテキスト、テーブル、進捗表示、例外トレースバックなどを表示できます。 |


### 5.3. 開発用の依存関係
開発、テスト、静的解析で使用するパッケージです。

```bash
uv add --dev pre-commit pyright pyyaml pytest pytest-mock ruff
```

| パッケージ | 説明 |
| --- | --- |
| `pytest` | `Python` のテストフレームワークです。<br />シンプルな `assert` を使って単体テストや結合テストを記述できます。 |
| `pytest-mock` | `pytest` からモックを扱いやすくするプラグインです。<br />`mocker` フィクスチャを利用して、関数やオブジェクトの差し替え、呼び出し検証などを行えます。 |
| `PyYAML` | リポジトリ検査スクリプトで `YAML` 設定ファイルを検証します。 |
| `ruff` | 高速な `Python` リンター／フォーマッターです。<br />コード品質のチェックとコードフォーマットを担当します。 |
| `pyright` | `Python` の静的型チェッカーです。<br />型ヒントを解析し、実行前に型の不整合を検出します。 |


#### 5.3.1. 開発ツール
各ツールの主な役割は以下のとおりです。

```text
pytest
└── Test
    └── コードが期待どおり動作するか検証

pytest-mock
└── Mock
    └── テスト対象の依存関係を差し替え

Ruff
├── Lint
│   └── コード上の問題を静的解析
└── Format
    └── コードスタイルを統一

Pyright
└── Type Check
    └── 型ヒントの不整合を静的解析
```


### 5.4. OpenSpec
`OpenSpec` はプロジェクトローカルの開発用依存関係としてインストールしています。

```bash
npm install --save-dev @fission-ai/openspec@latest
```

`Codex`、`Claude Code` 向けに `OpenSpec` を初期化しています。

```bash
npx --no-install openspec init --tools codex,claude
```

標準 profile に含まれないワークフロー（`new`、`continue`、`ff`、`verify`、`bulk-archive`、`onboard` など）が必要な場合は、profile で選択してから生成済み instruction を更新します。<br />
選択肢は OpenSpec のバージョンにより変わるため、対話プロンプトの表示例を固定せず、コマンドの案内に従って選択してください。

```bash
npx --no-install openspec config profile
npx --no-install openspec update
```

## 6. プロジェクト構成
```text
python-template/
├── .agents/              # AI エージェント用スキル
├── .claude/              # Claude Code
├── .gitignore             # Git の除外設定
├── .pre-commit-config.yaml # コミット時の基礎検査
├── openspec/             # OpenSpec specifications
│
├── scripts/              # リポジトリ運用・OpenSpec検査スクリプト
│
├── src/
│   └── app/
│
├── tests/
│
├── AGENTS.md              # AI 開発エージェントの共通指示
├── CLAUDE.md              # Claude Code 用の共通指示入口
├── pyproject.toml        # Python プロジェクト設定
├── uv.lock               # Python の依存関係ロックファイル
├── .python-version       # Python バージョン
│
├── package.json          # OpenSpec の依存関係
├── package-lock.json     # Node.js の依存関係ロックファイル
│
└── README.md
```


## 7. 依存関係の管理
`Python` パッケージを追加します。

```bash
uv add <package>
```

開発用のパッケージを追加します。

```bash
uv add --dev <package>
```

ロックファイルに従って依存関係を同期します。

```bash
uv sync --locked
```

依存関係を追加・更新した後は、ロックファイルを更新してから同期します。

```bash
uv lock
uv sync --locked
```

`OpenSpec` を含む `Node.js` の依存関係を同期します。

```bash
npm ci
```
