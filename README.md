# Visual Inspection SuperSimpleNet

SuperSimpleNetを使用し、型番ごとの画像準備、異常検出モデルの学習、外観検査をローカルCLIで実行するプロジェクトである。

大容量の元画像を基準画像へ位置合わせして分割し、正常画像中心のデータから評価用モデルと暫定閾値を生成する。<br />
検査では分割画像ごとの異常スコアと可視化画像を保存し、元画像・グループ単位の判定へ集約する。

> [!IMPORTANT]
> 現在のモデルと閾値は初期評価用である。<br />
> 異常スコアは校正済み確率ではなく、検出性能、誤検出率、処理時間の本番受け入れ基準も別途決定する必要がある。<br />
> このリポジトリのワークフローが完了したことだけを、本番利用の承認として扱わない。

## よく使う用語

初めて参加する開発者向けの説明である。<br />
振る舞いと受け入れ条件の正本は[外観検査仕様](openspec/specs/visual-inspection/README.md)と[group-scoped-inspection-models change](openspec/changes/archive/2026-10-09-group-scoped-inspection-models/proposal.md)に置く。

| 用語 | 意味 |
| --- | --- |
| 型番 / `model` | CLI の `--model` で指定する対象製品の識別子。学習済みモデルそのものは指さない |
| 分割 / `range` | 基準画像上の左上座標と分割IDで定義する切り出し範囲 |
| グループ / `group` | 共通の分割IDを参照し、学習・検査条件と学習済みモデルを独立して持つ単位 |
| 基準画像 | 元画像の位置合わせ先となる画像 |
| 元画像 | 学習または検査に入力する、分割前の画像 |
| 分割画像 | 元画像を位置合わせし、設定範囲で切り出した画像 |
| 準備manifest | 元画像と分割画像の対応、準備条件の指紋を記録するJSON |
| 準備指紋 | 分割画像を作る設定のハッシュ。学習・検査開始時に準備結果との一致を確認する |
| checkpoint | グループの学習済みモデルと型番・グループ・暫定閾値のメタデータ |
| 異常スコア | SuperSimpleNetの`pred_score`。校正済み確率ではない |
| 異常マップ | 分割画像の画素ごとの`anomaly_map`。ヒートマップ表示に使う |
| 暫定閾値 | 学習集合の異常スコアから算出する、初期評価用の判定境界 |
| 検査用閾値 | グループの`inspection_threshold`。指定時に暫定閾値に代えて使う |
| `undetermined` | 位置合わせ失敗や分割不足などで正常と確定できないグループ内判定 |
| 結果世代 | 1回の`test`で完成させる、グループ別の結果画像とJSONの一式 |
| 現行参照 | `current.json`に記録する、各グループで現在使用する結果世代の相対パス |
| capability | 継続して管理する機能・責務の単位。このプロジェクトでは画像準備、モデル学習、モデル評価の3つ |
| OpenSpec change | 一回の変更を計画・実装・検証する単位 |

## 動作環境

- Python 3.13と`uv`
- Ubuntu 24.04 LTSまたはWindows 11 (x86-64)
- CUDA対応GPUは任意。利用できない場合はCPUを使う
- Node.js 22とnpm (OpenSpec操作と開発時の品質検査)

依存関係を同期する。

```bash
uv sync --locked
npm ci
```

## 外観検査ワークフロー

### 1. 入力と設定

`<model>`には英数字から始まる英数字・`_`・`-`を使用する。<br />
`config/setting.ini`の`IMAGE.SIZE`に分割画像の一辺、`IMAGE.RESIZE`に位置合わせ前の縮小倍率を指定する。<br />
`RESIZE`を省略した場合は1を使用する。<br />
`range`の`x`と`y`は縮小前の基準画像で指定し、縮小後も分割画像の一辺には`SIZE`を使用する。

型番ごとに[part_XX.json](config/part_XX.json)をひな形として`config/part_<model>.json`を用意する。<br />
基準画像と学習元画像を`data/01_original_train/<model>/`、試験元画像を`data/02_original_test/<model>/`に置く。

| 設定項目 | 内容 |
| --- | --- |
| `base` | 学習元画像領域直下の基準画像名 |
| `range` | 一意な分割IDと縮小前の開始座標の配列 |
| `blacklist` | 学習準備だけで除外する元画像名と分割ID |
| `alignment` | 型番内で共通のORB位置合わせ条件 |
| `groups` | 必須の非空配列。グループIDは型番内で一意な非負整数 |
| `groups[].range_ids` | 非空・重複なしの既存分割ID。同じ分割IDを複数グループで参照できる |
| `groups[].optuna_settings` | グループ別の探索、学習・検証分離、暫定閾値 |
| `groups[].score` | `supersimplenet.pred_score`と無効化したPostProcessor |
| `groups[].augmentation` | 学習入力だけに適用する拡張条件 |
| `groups[].inspection_threshold` | `null`なら暫定閾値。0以上1以下の数値なら検査で使用 |
| `groups[].heatmap_range` | 検査時に必須の有限な下限・上限。`min < max` |

`blacklist`と`alignment`は型番共通である。<br />
暫定閾値の`groups[].optuna_settings.threshold.value`は学習完了時に対象グループだけ更新される。<br />
checkpointと最良試行にも同じ値を保存するため、暫定閾値だけを手動で変更しない。<br />
切り出し位置、サイズ、縮小倍率、位置合わせなどを変更したら、該当する`train-pre`または`test-pre`を再実行する。<br />
準備指紋が一致しない入力は学習・検査の前に拒否される。

### 2. 確認・学習・検査

```bash
uv run --locked check --model XX
uv run --locked train-pre --model XX
uv run --locked train --model XX
uv run --locked test-pre --model XX
uv run --locked test --model XX
```

`check`は全分割と各グループの確認画像を作る。<br />
`train-pre`と`train`は省略時に全グループをID昇順で処理する。<br />
`test-pre`は常に全分割を一度準備し、`test`は省略時に全グループを検査する。<br />
単独グループを操作する場合は次のように指定する。

```bash
uv run --locked train-pre --model XX --group 1
uv run --locked train --model XX --group 1
uv run --locked test --model XX --group 1
```

学習探索履歴とcheckpointを対象グループで作り直す場合は`train --restart`を使う。<br />
`test`は実行のたびに対象グループの結果を新しく作るため、`--restart`は受け付けない。<br />
全件学習で後続グループが失敗した場合、コマンドはエラー終了し、失敗グループIDを表示する。<br />
完了済みグループの成果物は保持する。<br />
全件検査では対象グループのモデル一式を推論前に照合し、一つでも欠ければ結果を更新しない。<br />
検査中に失敗した場合も`current.json`を切り替えず、旧結果を保持する。

元画像の判定はグループごとに、`anomaly`が一つでもあれば`anomaly`、必要な全分割が`normal`なら`normal`、それ以外は`undetermined`とする。<br />
グループ間の総合判定は作らない。

### 成果物と読戻し

| 成果物 | 保存先 |
| --- | --- |
| 全分割と各グループの確認画像 | `data/03_check/<model>/all.png`、`group_<id>.png` |
| グループ別学習準備 | `data/04_train/<model>/group_<id>/` |
| 全分割の試験準備 | `data/05_test/<model>/` |
| グループ別探索と最良試行 | `optuna/<model>/group_<id>/` |
| グループ別checkpoint | `weights/<model>/group_<id>.ckpt` |
| 現行結果参照 | `data/06_result/<model>/current.json` |
| 検査結果画像と元画像・グループ別JSON | `data/06_result/<model>/generations/<実行ID>/group_<id>/` |

`current.json`の`groups`は、グループIDをキーとして`generations/<実行ID>/group_<id>`への相対パスを示す。<br />
結果を読む側は、同じ型番の`test`が動いていない時に`current.json`を一度読み、示されたJSONと画像を読む。<br />
単独検査では他グループの参照を保持する。<br />
参照の切替後、参照されなくなったグループ結果と空の世代を整理し、現在の各グループ結果だけを残す。<br />
整理に失敗した場合は警告を記録し、次の型番コマンドで再試行する。<br />
現行参照が壊れている場合、単独検査と読戻しは拒否されるが、全件`test`で新しい結果一式を作って参照を再生成できる。

同じ型番の5コマンドは同時実行できない。<br />
後から起動したコマンドは型番を示して終了コード3で拒否する。<br />
異なる型番は並行して処理できる。<br />
各コマンドは標準出力に実行記録JSONを1件出し、処理段階、警告、失敗理由は標準エラーへ表示する。<br />
終了コード0は成功、2は設定や入力の不備、3は処理失敗や同じ型番の同時実行を示す。

## 実機スモーク試験

Ubuntu 24.04 LTSとWindows 11の対象実機で、CPUと利用可能なGPUによる全件・単独グループの実行と成果物読戻しを確認する。<br />
`--output`には実行ごとに異なるパスを指定する。

```bash
uv run --locked python scripts/run_visual_inspection_smoke.py --model XX --output smoke/all.json
uv run --locked python scripts/run_visual_inspection_smoke.py --model XX --group 1 --output smoke/group-1.json
```

結果JSONは対象OS、Python、依存版、使用デバイス、実行状態、保存先の読戻し結果を記録する。<br />
本番利用の性能・誤検出基準は別途評価する。

## 仕様

正式仕様は`openspec/specs/`で管理し、今回のグループ単位の変更は[group-scoped-inspection-models](openspec/changes/archive/2026-10-09-group-scoped-inspection-models/proposal.md)で追跡する。<br />
画像準備、モデル学習、モデル評価の責務・共有契約・依存方向は[配置案内](openspec/structure.md)を参照する。

## 開発

### 文書の書き方

README などの日本語の案内文書では、本文の文末の句点の直後で原則改行する。<br />
同じ段落を続ける場合は `。<br />` の後で改行し、段落を分ける場合は空行を入れる。<br />
表のセル、コードブロック、見出しなどは読みやすさを優先する。<br />
括弧には半角の `(` と `)` を使う。

コミット前の基礎検査を実行する。<br />
初回だけpre-commitフックを有効化する。

```bash
uv run --locked pre-commit install
uv run --locked pre-commit run --all-files
```

統合前の品質検査は、OpenSpecの検証、format、lint、型検査、テスト、リポジトリ検査、進行中changeのトレーサビリティ検査をまとめて実行する。

```bash
npm run check
```

個別に実行する場合は次のコマンドを使用する。

```bash
uv run --locked pytest
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pyright
npx --no-install openspec validate --all --strict
```

OpenSpec change の対応検査は工程に応じて実行する。<br />
既定の設計段階では要件・Scenario・試験ケース・タスクの対応と参照書式を確認し、未作成のテストと未完了タスクを許容する。

```bash
# 設計段階
uv run --locked python scripts/check_openspec_traceability.py --change <change-name>

# 実装後: 参照する pytest テストの収集可否も確認
uv run --locked python scripts/check_openspec_traceability.py --change <change-name> --phase implementation

# 通常の完了時: 全タスク、受け入れ条件と証跡も確認
uv run --locked python scripts/check_openspec_traceability.py --change <change-name> --phase complete

# 実機確認だけを延期して制限付きでアーカイブする場合
uv run --locked python scripts/check_openspec_traceability.py --change <change-name> --phase limited-archive
```

proposal の受け入れ条件には `AC-001` 形式のIDを付け、design の「受け入れ検証」に検証範囲・方法・残る検証・状態・証跡を対応付ける。<br />
通常の完了段階では全条件を検証済みとし、残る検証を「なし」にして、リポジトリ相対パスの空でない証跡ファイルを用意する。<br />
自動試験の収集と成功は、実機や対象OSでの確認を代替しない。

実機など利用できない環境での受け入れ確認だけが残る場合は、この README の「延期中の受け入れ確認」に change 名、AC-ID、状態「未検証」、未完了タスク番号と確認内容を記録し、明示的な了承を得て制限付きでアーカイブできる。<br />
`archive-deferred.md`、実施責任者・再開条件、GitHub Issue や別の spec の作成は必須ではない。<br />
延期した条件は未検証のままにし、運用開始の承認とは扱わない。<br />
実装・自動試験・品質確認の未完了や重要な未解決事項があれば change を進行中に残す。<br />
詳細は[技術基盤](openspec/tech.md)を参照する。

OpenSpecを更新する場合は、プロジェクトローカルのCLIとロックファイルを先に更新し、生成済みのエージェント向けinstructionsを更新する。

```bash
npm install --save-dev @fission-ai/openspec@latest
npx --no-install openspec update
```

## 配置と依存境界の検証記録

`organize-app-by-capability` の AC-001 は、[配置案内](openspec/structure.md)で3能力と `src/app/common/` の対応を確認した。<br />
2026-10-05、macOS 26.6.2 arm64・Python 3.13.15 で `uv run --locked pytest tests/test_package_structure.py::test_capability_import_boundaries -q` を実行し、1件成功した。<br />
検査は能力間の直接 import と `common/` から能力への import を禁止する。

## 延期中の受け入れ確認

実機確認を延期している change と AC-ID を記録する。<br />
検証後は状態と証跡を更新し、change の受け入れ検証記録にも結果を反映する。

| change | 受け入れID | 状態 | 記録 |
| --- | --- | --- | --- |
| group-scoped-inspection-models | AC-007 | 未検証 | タスク6.7: Ubuntu 24.04 LTS・Windows 11の対象実機でCPUと利用可能なGPUを使い、全件・単独グループの5 CLIと成果物読戻しを確認する。 |
| group-scoped-inspection-models | AC-008 | 未検証 | タスク6.8: 両OSで同一型番・別型番の同時起動、終了コード3の拒否、中断後の復旧を確認する。 |
| organize-app-by-capability | AC-002 | 未検証 | タスク4.3: Ubuntu 24.04 LTS・Windows 11 の実機で5 CLIの名前・引数・終了コード・出力を確認する。 |
| organize-app-by-capability | AC-003 | 未検証 | タスク4.4: 両OSの実機でmanifest・checkpoint・検査結果の形式、保存先、読戻しを確認する。 |
| organize-app-by-capability | AC-004 | 未検証 | タスク4.5: 両OSでGPU有効・無効の計4条件を実行し、学習・推論で実際に使用したデバイスを確認する。 |
| resize-and-knn-image-alignment | AC-001 | 未検証 | タスク4.1: Ubuntu 24.04 LTS・Windows 11の実機で倍率0.5の確認・学習・試験を実行し、縮小後の寸法、座標、切り出しSIZE、元画像の不変を確認する。 |
| resize-and-knn-image-alignment | AC-002 | 未検証 | タスク4.2: 両OSの実機で運用画像によるKNN比率判定と位置合わせの成功・失敗、処理時間、縮小・分割画像の画質を確認する。 |
| resize-and-knn-image-alignment | AC-003 | 未検証 | タスク4.3: 両OSの実機で不正設定、範囲外・0寸法、位置合わせ失敗を確認し、終了コード、旧成果物維持、学習除外と試験未判定を確認する。 |
| fix-anomalib-training-checkpoint | AC-001 | 未検証 | タスク3.1: Ubuntu 24.04 LTSで元画像単位に分けた検証画像が追加分割されず全件利用されることを確認する。 |
| fix-anomalib-training-checkpoint | AC-002 | 未検証 | タスク3.2: Ubuntu 24.04 LTSで試行ごとの学習率倍率を維持してcheckpointを保存できることを確認する。 |
| fix-anomalib-training-checkpoint | AC-003 | 未検証 | タスク3.3: Ubuntu 24.04 LTSでPreProcessor入りcheckpointのメタデータを読み込み、契約照合を通過して検査を開始できることを確認する。 |
| fix-anomalib-training-checkpoint | AC-004 | 未検証 | タスク3.4: Ubuntu 24.04 LTSで学習から検査までを実行し、報告された3件のエラーなく完了することを確認する。 |
| improve-inspection-configuration-and-cli | AC-001 | 未検証 | タスク4.1: 対象OSと実モデルで暫定・検査用閾値による判定と学習成果物の整合を確認する。 |
| improve-inspection-configuration-and-cli | AC-003 | 未検証 | タスク4.2: Ubuntu 24.04 LTSとWindows 11で5 CLIの段階表示、準備進捗、標準出力JSON、終了コードを確認する。 |
| improve-inspection-configuration-and-cli | AC-004 | 未検証 | タスク4.3: 実際の基準画像で縮小前座標、確認画像、学習・試験の切り出し位置と`SIZE`を照合する。 |
| improve-inspection-configuration-and-cli | AC-005 | 未検証 | タスク4.4: 対象環境で不正設定・位置合わせ失敗・途中処理失敗の理由、終了状態、旧成果物保全と未判定を確認する。 |
| improve-inspection-configuration-and-cli | AC-006 | 未検証 | タスク4.5: 対象型番の旧座標と分割画像を比較し、必要な再学習・検査結果再生成と旧成果物の退避を確認する。 |
| comparable-heatmap-scale | AC-001 | 未検証 | タスク4.2: Ubuntu 24.04 LTS・Windows 11で同一学習済みモデルと表示範囲を確認し、異なる異常マップの同値同色をヒートマップ層で確認する。 |
| comparable-heatmap-scale | AC-002 | 未検証 | タスク4.3: 両OSで正常画像の非着色、異常画像の着色、スコア・閾値・判定の独立性を確認する。 |
| comparable-heatmap-scale | AC-003 | 未検証 | タスク4.4: 両OSで表示範囲変更後の`test`と結果JSONの表示範囲を確認する。 |
| comparable-heatmap-scale | AC-004 | 未検証 | タスク4.5: 両OSで未指定・不正な表示範囲のCLI拒否と新結果が作られないことを確認する。 |
| show-test-progress-and-update-backbone | AC-001 | 未検証 | タスク4.1: Ubuntu 24.04 LTS・Windows 11の端末・非端末で`test`の元画像進捗、標準出力JSONと終了コードを確認する。 |
| show-test-progress-and-update-backbone | AC-002 | 未検証 | タスク4.2: 両OSの実画像で未判定・個別分割エラー・全体失敗時の進捗と終了状態を確認する。 |
| show-test-progress-and-update-backbone | AC-003 | 未検証 | タスク4.3: 対象型番で`racm_in1k`実重みの取得、再学習、checkpointによる検査を確認する。 |
| show-test-progress-and-update-backbone | AC-004 | 未検証 | タスク4.4: 全型番で旧探索履歴・checkpointの破棄、閾値・表示範囲の見直し、旧検査結果の再生成を確認する。 |
| restore-tv-backbone-and-improve-output | AC-001 | 未検証 | タスク5.1: Ubuntu 24.04 LTSとWindows 11で`tv_in1k`の実重みを取得して学習し、checkpointによる検査を確認する。 |
| restore-tv-backbone-and-improve-output | AC-002 | 未検証 | タスク5.2: 対象の全型番で旧成果物を退避し、`train --restart`、閾値と表示範囲の確認、`test`を実施する。 |
| restore-tv-backbone-and-improve-output | AC-003 | 未検証 | タスク5.3: 両OSの実画像で正常分割と、異常分割の左原画像・右ヒートマップ付き画像を結果JSONと照合する。 |
| restore-tv-backbone-and-improve-output | AC-004 | 未検証 | タスク5.4: 両OSの端末・非端末で試行条件表、終了状態、再開時の件数、標準出力JSONと終了コードを確認する。 |

`show-test-progress-and-update-backbone` のAC-003にある`racm_in1k`確認は当時の未検証事項であり、現在の運用には適用しない。<br />
現在のバックボーンと移行確認は`restore-tv-backbone-and-improve-output`で扱う。

`comparable-heatmap-scale` の実機確認時は、[アーカイブ済みchangeの検証記録](openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md)にモデル確認方法、使用範囲、結果画像・JSON、実行コマンド、環境、日付、制約を追記する。<br />
AC-001〜AC-004 は未検証であり、自動試験の成功やアーカイブは運用開始の承認を意味しない。

タスク4.3〜4.5の実行時は各条件で別の出力先を使い、OS・Python・依存版、GPU無効化方法、5 CLIの結果、成果物の読戻し、実測デバイスを change 内の `evidence/acceptance.md` へ記録する。<br />
現時点では実機確認と運用受け入れは完了していない。

`fix-anomalib-training-checkpoint` のタスク3.1〜3.4では、Ubuntu 24.04 LTSで学習から検査まで実行し、条件・結果を[アーカイブ済みchangeの検証記録](openspec/changes/archive/2026-10-07-fix-anomalib-training-checkpoint/evidence/acceptance.md)へ記録する。<br />
自動試験は成功しているが、対象OSでの一連の実行結果は未検証であり、運用開始の承認を意味しない。
