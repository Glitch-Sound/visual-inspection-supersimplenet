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
| グループ / `group` | 共通の分割IDを参照し、学習条件と学習済みモデルを独立して持ち、分割ごとの検査条件をまとめる単位 |
| グループ詳細 / `group_detail` | グループIDをキーに、探索条件・スコア契約・データ拡張をまとめた型番設定の領域 |
| 擬似異常 / `synthetic_anomaly` | SuperSimpleNetが学習中に作る異常。ノイズの強さ、範囲、かたまりの細かさをグループごとに指定する |
| 初期ランダム探索試行数 / `sampler.startup_trials` | グループの TPESampler が TPE による探索へ移る前の試行数。MedianPruner の同名項目とは別 |
| 基準画像 | 元画像の位置合わせ先となる画像 |
| 元画像 | 学習または検査に入力する、分割前の画像 |
| 分割画像 | 元画像を位置合わせし、設定範囲で切り出した画像 |
| 輝度補正 / `brightness_normalization` | 学習・試験準備の分割画像の明るさを、同じ範囲の基準画像に近づける処理 |
| 準備manifest | 元画像と分割画像の対応、準備条件の指紋を記録するJSON |
| 再撮影要否 / `recapture_required` | 位置合わせ結果に記録する、再撮影が原則必要な状態。試験準備結果から検査結果にも引き継ぐ |
| 準備指紋 | 分割画像を作る設定のハッシュ。学習・検査開始時に準備結果との一致を確認する |
| checkpoint | グループの学習済みモデルと型番・グループ・暫定閾値のメタデータ |
| 異常スコア | SuperSimpleNetの`pred_score`。校正済み確率ではない |
| 異常マップ | 分割画像の画素ごとの`anomaly_map`。ヒートマップ表示に使う |
| 暫定閾値 | 学習集合の異常スコアから算出する、初期評価用の判定境界 |
| 検査用閾値 | `groups[].ranges[].inspection_threshold`。分割ごとに指定し、`null` ならグループの暫定閾値を使う |
| `undetermined` | 位置合わせ失敗や分割不足などで正常と確定できないグループ内判定 |
| グループ結果 | `test`が `data/06_result/<model>/group_<2桁以上のID>/` に保存する、グループの最新の結果画像とJSONの一式 |
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
| `brightness_normalization` | 型番共通の分割画像の輝度補正。項目全体の省略時は無効。記述時の既定値は `enabled=true`、`statistic=median`、`exclude_above=230`、`exclude_below=0`、`min_gain=0.5`、`max_gain=2.0` |
| `groups` | 必須の非空配列。グループIDは型番内で一意な非負整数。分割ごとの検査条件を置く |
| `groups[].ranges` | 必須の非空配列。各要素に `id`、`inspection_threshold`、`heatmap_range` を必ず書く。グループ単位の上書きや既定値はない |
| `groups[].ranges[].id` | 共通 `range` にある分割ID。同じグループ内では重複不可。同じIDを複数グループで参照できる |
| `groups[].ranges[].inspection_threshold` | `null` ならそのグループの暫定閾値。0以上1以下の有限数値なら当該分割の検査に使用 |
| `groups[].ranges[].heatmap_range` | 各分割で必須の有限な下限・上限。`min < max` |
| `group_detail` | グループIDの通常の10進文字列をキーにする詳細設定。`groups`のIDと一対一に対応 |
| `group_detail["<id>"].optuna_settings` | グループ別の探索、学習・検証分離、暫定閾値 |
| `group_detail["<id>"].optuna_settings.sampler.startup_trials` | TPESampler の初期ランダム探索試行数。0以上の整数で、省略時は5 |
| `group_detail["<id>"].score` | `supersimplenet.pred_score`と無効化したPostProcessor |
| `group_detail["<id>"].augmentation` | 学習入力だけに適用する拡張条件 |
| `group_detail["<id>"].synthetic_anomaly` | 学習中の擬似異常生成範囲。`noise_std` は `0.010`〜`0.020`、`perlin_threshold` は `0.2`〜`0.4`、`perlin_scale_exponent` は整数 `0`〜`5` が省略時の推奨値。各項目は `min` と `max` で指定する |

`blacklist`、`alignment`、`brightness_normalization`は型番共通である。<br />
旧形式の `groups[].range_ids`、グループ単位の `inspection_threshold` と `heatmap_range` は使用できない。<br />
分割ごとの検査閾値と表示範囲が不正な場合、5つのコマンドはいずれも入力不備として終了し、既存成果物を更新しない。<br />
輝度補正は`train-pre`と`test-pre`の分割画像に適用する。<br />
`statistic`は`median`または`mean`を指定し、`exclude_below`以上・`exclude_above`未満の輝度を集計する。<br />
集計できる画素がない場合や分割画像の輝度が0以下の場合は、その分割の補正を省略する。<br />
補正を無効にするには項目全体を省略するか`enabled=false`を指定する。<br />
例えば`id: 0`に対応するキーは`"0"`とし、`"00"`は使用しない。<br />
`groups` に置けない詳細項目や、両領域で項目が重複する設定は入力不備として拒否される。<br />
`sampler.startup_trials` はグループごとに設定する。<br />
TPE による探索を行うには、`sampler.startup_trials` を合計試行回数の `execution.trials` より小さくする。<br />
同じ値以上にすると、設定された試行はすべて初期ランダム探索となり、TPE による探索は行われない。<br />
暫定閾値の`group_detail["<id>"].optuna_settings.threshold.value`は学習完了時に対象グループだけ更新される。<br />
暫定閾値はグループ単位で算出し、分割ごとには算出しない。<br />
checkpointと最良試行にも同じ値を保存するため、暫定閾値だけを手動で変更しない。<br />
学習時に使用した擬似異常の設定範囲もcheckpointと`best_trial.json`の両方に記録する。<br />
切り出し位置、サイズ、縮小倍率、位置合わせなどを変更したら、該当する`train-pre`または`test-pre`を再実行する。<br />
準備指紋が一致しない入力は学習・検査の前に拒否される。

分割ごとの `inspection_threshold` または `heatmap_range` だけを変更した場合、準備指紋は変わらない。<br />
準備と学習をやり直さず、`test` のみ再実行できる。

輝度補正条件を変更した場合は、旧成果物を引き継がず、`train-pre`、`train`、`test-pre`、`test`を順に再実行する。<br />
分割位置も確認したい場合は先に`check`を実行する。

擬似異常生成範囲を変更した場合は、旧成果物を引き継がず、`check`、`train-pre`、`train`、`test-pre`、`test`を順に再実行する。<br />
`noise_std` は `0 < min <= max`、`perlin_threshold` は `0 <= min <= max < 1`、`perlin_scale_exponent` は整数で `0 <= min <= max <= 5` とする。<br />
`min = max` なら固定値を使う。<br />
擬似異常の範囲は学習時だけに適用し、Optuna の探索対象にはしない。

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

`train`は実行のたびに対象グループの探索と学習を最初から行う。<br />
5コマンドは開始時に対象型番の前回残った管理対象一時領域を全グループ分削除する。<br />
`train-pre`、`train`、`test-pre`は一時領域で成果物を完成させ、対象の旧成果物を削除してから新成果物を公開する。<br />
`test`は全対象グループの結果を一時領域で完成させ、グループごとに旧結果を削除して新結果を公開する。<br />
公開前に失敗・中断した場合は旧結果を保持し、一時結果は削除する。<br />
公開途中の中断で結果が欠けた場合は`test`を再実行する。<br />
新旧が混在した場合は全件`test`で解消する。<br />
結果の直接読戻しは同型番の検査が止まり、必要な再実行を終えた後に行う。
全件学習で後続グループが失敗した場合、コマンドはエラー終了し、失敗グループIDを表示する。<br />
完了済みグループの成果物は保持する。<br />
全件学習では成功したグループから学習成果物を置き換える。<br />
全件検査では全対象の作成を終えてから公開し、作成中に後続グループが失敗した場合は失敗グループIDと理由を示して終了し、全対象グループの旧結果を保持する。<br />
各グループのモデル一式はそのグループの推論前に照合する。

元画像の判定はグループごとに、`anomaly`が一つでもあれば`anomaly`、必要な全分割が`normal`なら`normal`、それ以外は`undetermined`とする。<br />
各分割は `pred_score >=` 使用閾値を `anomaly` とし、結果JSONの分割結果に使用閾値、その出どころ (`provisional` または `configured`)、ヒートマップ表示範囲を記録する。<br />
グループ単位の `threshold` と `heatmap_range` は結果JSONに置かない。<br />
検査開始時もグループID・分割IDごとの使用閾値と出どころを表示する。<br />
グループ間の総合判定は作らない。

### 成果物と読戻し

| 成果物 | 保存先 |
| --- | --- |
| 全分割と各グループの確認画像 | `data/03_check/<model>/all.png`、`group_<2桁以上のID>.png` |
| グループ別学習準備 | `data/04_train/<model>/group_<2桁以上のID>/` |
| 全分割の試験準備 | `data/05_test/<model>/` |
| グループ別探索と最良試行 | `optuna/<model>/group_<2桁以上のID>/` |
| グループ別checkpoint | `weights/<model>/group_<2桁以上のID>.ckpt` |
| 検査結果画像と元画像・グループ別JSON | `data/06_result/<model>/group_<2桁以上のID>/` |

グループ別成果物の名前だけIDを最低2桁で0埋めする (ID `0` は `group_00`、ID `100` は `group_100`)。<br />
設定、CLI、各JSONのID値は整数である。<br />
破壊的変更後は既存の準備・学習・検査成果物および型番設定との互換性を前提とせず、`check`、`train-pre`、`train`、`test-pre`、全件`test`の順に再実行する。<br />
各グループの直下には`<元画像名>.json`と`<分割画像名>_result.png`だけを置く。<br />
結果を読む側は同じ型番の`test`が動いていない時にグループ別フォルダを直接開く。<br />
単独検査では指定グループだけを置き換え、他グループの結果を変更しない。<br />
全件検査では型番設定にないグループ結果を削除する。<br />
変更後は旧準備・学習・検査成果物を引き継がず、準備・学習・検査を順に再実行する。<br />
検査完了時は`data/06_result/<model>/`を表示する。

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
| per-range-threshold-and-heatmap | AC-001 | 未検証 | タスク5.2: Ubuntu 24.04 LTS・Windows 11で同じ分割IDを複数グループに設定し、それぞれの閾値・表示範囲を確認する。 |
| per-range-threshold-and-heatmap | AC-002 | 未検証 | タスク5.2: 両OSの5コマンドで分割条件の欠落・不正・旧項目を拒否し、旧成果物を保持することを確認する。 |
| per-range-threshold-and-heatmap | AC-003 | 未検証 | タスク5.2: 両OSのCPUと利用可能なGPUで、分割別の判定境界・ヒートマップ・元画像判定を実画像で確認する。 |
| per-range-threshold-and-heatmap | AC-004 | 未検証 | タスク5.2: 両OSで分割別の使用閾値・出どころ・表示範囲を結果JSONと検査開始表示で照合する。 |
| per-range-threshold-and-heatmap | AC-005 | 未検証 | タスク5.2: 両OSで内部の分割IDと準備指紋を確認し、検査値だけを変えて準備・学習なしで再検査する。 |
| per-range-threshold-and-heatmap | AC-006 | 未検証 | タスク5.2: 両OSで新形式設定を使って全工程を再実行し、成果物の読戻しと案内手順を確認する。 |
| configure-synthetic-anomaly-generation | AC-001 | 未検証 | タスク4.2: Ubuntu 24.04 LTS・Windows 11の実画像でグループ別の3範囲、省略値、maskごとの選択を確認する。 |
| configure-synthetic-anomaly-generation | AC-002 | 未検証 | タスク4.2: 両OSの学習CLIで不正な範囲・型の拒否、旧成果物の保持、設定修正後の再実行を確認する。 |
| configure-synthetic-anomaly-generation | AC-003 | 未検証 | タスク4.2: 両OSのCPUと利用可能なGPUで、擬似異常の50%判定、生成手順、学習seedによる再現を確認する。 |
| configure-synthetic-anomaly-generation | AC-004 | 未検証 | タスク4.2: 両OSで探索条件に擬似異常を含めず、5 CLIを再実行してcheckpointから既存形式の検査結果を読み戻す。 |
| configure-synthetic-anomaly-generation | AC-005 | 未検証 | タスク4.2: 両OSの実画像で異なるグループ設定の学習・検査と成果物読戻しを確認し、検出性能は別途評価する。 |
| configure-tpe-startup-trials | AC-001 | 未検証 | タスク3.2: Ubuntu 24.04 LTS・Windows 11の実画像で指定値・省略時・合計試行回数以上の探索を確認する。 |
| configure-tpe-startup-trials | AC-002 | 未検証 | タスク3.2: 両OSの学習CLIで負数・非整数の入力不備と修正後の再実行を確認する。 |
| configure-tpe-startup-trials | AC-004 | 未検証 | タスク3.2: 両OSの実画像でMedianPrunerの条件と、準備・学習・検査の全工程を確認する。 |
| drop-legacy-and-recovery-handling | AC-001 | 未検証 | タスク3.3: Ubuntu 24.04 LTS・Windows 11で四CLIの公開前失敗、旧成果物の保持、残存一時領域の削除を確認する。 |
| drop-legacy-and-recovery-handling | AC-002 | 未検証 | タスク3.3: 両OSの実モデルで毎回の新規探索と全グループ途中失敗時の部分成功、失敗グループIDと理由を確認する。 |
| drop-legacy-and-recovery-handling | AC-003 | 未検証 | タスク3.3: 両OSで学習成果物公開後の対象閾値書戻しと他設定・別グループの保持を確認する。 |
| drop-legacy-and-recovery-handling | AC-004 | 未検証 | タスク3.3: 両OSで公開途中の中断による成果物の欠落・不整合の拒否と、準備・学習・検査の再実行案内を確認する。 |
| drop-legacy-and-recovery-handling | AC-005 | 未検証 | タスク3.3: 両OSで準備指紋、最良試行とcheckpointの整合、型番排他、シンボリックリンク拒否と四CLIの実行を確認する。 |
| split-group-config-details | AC-001 | 未検証 | タスク3.3: Ubuntu 24.04 LTS・Windows 11の対象環境で新形式の複数グループ設定を使い、5 CLIの全件・単独実行と成果物読戻しを確認する。 |
| split-group-config-details | AC-002 | 未検証 | タスク3.4: 両OSで詳細の欠落・余分・非標準IDキーと`groups`に置けない項目を入力不備として拒否し、既存成果物が変わらないことを確認する。 |
| split-group-config-details | AC-003 | 未検証 | タスク3.5: 両OSで実モデルの単独グループ学習を行い、対象の暫定閾値だけが詳細設定へ書き戻されることを確認する。 |
| pad-group-artifact-names | AC-001 | 未検証 | タスク3.3: Ubuntu 24.04 LTS・Windows 11の対象環境でID 0・10のグループ別成果物名と整数IDを全CLIで確認する。 |
| align-inspection-progress-and-scenario-tests | AC-001 | 未検証 | タスク4.1: 対象OSの実端末・非端末で全・単独グループ検査の元画像進捗、途中失敗、標準出力JSONを確認する。 |
| align-inspection-progress-and-scenario-tests | AC-002 | 未検証 | タスク4.2: 対象OSの実画像と実GPU/CPUで準備、判定画像、色尺度、CLI表示を確認する。 |
| align-inspection-progress-and-scenario-tests | AC-003 | 未検証 | タスク4.3: 実重みで指定グループを再学習し、checkpointによる検査と他グループ保持を確認する。 |
| group-scoped-inspection-models | AC-007 | 未検証 | タスク6.7: Ubuntu 24.04 LTS・Windows 11の対象実機でCPUと利用可能なGPUを使い、全件・単独グループの5 CLIと成果物読戻しを確認する。 |
| group-scoped-inspection-models | AC-008 | 未検証 | タスク6.8: 両OSで同一型番・別型番の同時起動、終了コード3の拒否、中断後の欠落検出と再実行を確認する。 |
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
| comparable-heatmap-scale | AC-001 | 未検証 | タスク4.2: Ubuntu 24.04 LTS・Windows 11で同一学習済みモデルと表示範囲を確認し、異なる異常マップの同値同色をヒートマップ層で確認する。 |
| comparable-heatmap-scale | AC-002 | 未検証 | タスク4.3: 両OSで正常画像の非着色、異常画像の着色、スコア・閾値・判定の独立性を確認する。 |
| comparable-heatmap-scale | AC-003 | 未検証 | タスク4.4: 両OSで表示範囲変更後の`test`と結果JSONの表示範囲を確認する。 |
| comparable-heatmap-scale | AC-004 | 未検証 | タスク4.5: 両OSで未指定・不正な表示範囲のCLI拒否と新結果が作られないことを確認する。 |
| show-test-progress-and-update-backbone | AC-001 | 未検証 | タスク4.1: Ubuntu 24.04 LTS・Windows 11の端末・非端末で`test`の元画像進捗、標準出力JSONと終了コードを確認する。 |
| show-test-progress-and-update-backbone | AC-002 | 未検証 | タスク4.2: 両OSの実画像で未判定・個別分割エラー・全体失敗時の進捗と終了状態を確認する。 |
| show-test-progress-and-update-backbone | AC-003 | 未検証 | タスク4.3: 対象型番で`racm_in1k`実重みの取得、再学習、checkpointによる検査を確認する。 |
| show-test-progress-and-update-backbone | AC-004 | 未検証 | タスク4.4: 全型番で旧探索履歴・checkpointの破棄、閾値・表示範囲の見直し、旧検査結果の再生成を確認する。 |
| restore-tv-backbone-and-improve-output | AC-001 | 未検証 | タスク5.1: Ubuntu 24.04 LTSとWindows 11で`tv_in1k`の実重みを取得して学習し、checkpointによる検査を確認する。 |
| restore-tv-backbone-and-improve-output | AC-003 | 未検証 | タスク5.3: 両OSの実画像で正常分割と、異常分割の左原画像・右ヒートマップ付き画像を結果JSONと照合する。 |
| restore-tv-backbone-and-improve-output | AC-004 | 未検証 | タスク5.4: 両OSの端末・非端末で試行条件表、終了状態、毎回の新規探索件数、標準出力JSONと終了コードを確認する。 |
| add-brightness-normalization | AC-001 | 未検証 | タスク3.5: Ubuntu 24.04 LTS・Windows 11でmedian・mean・無効化の学習・試験分割画像を読み戻して確認する。 |
| add-brightness-normalization | AC-002 | 未検証 | タスク3.5: 両OSで値なし・対象輝度0の分割が補正前画素で保存されることを確認する。 |
| add-brightness-normalization | AC-003 | 未検証 | タスク3.5: 両OSのCLIで不正な補正設定の入力不備表示・終了コード2と既存成果物の保持を確認する。 |
| add-brightness-normalization | AC-004 | 未検証 | タスク3.5: 両OSで有効時の全補正項目の変更が学習・試験指紋に反映され、旧成果物が拒否されることを確認する。 |
| add-brightness-normalization | AC-005 | 未検証 | タスク3.5: 両OSのCPUと利用可能なGPUで準備・学習・検査を全件・単独グループでやり直し、成果物を読み戻す。 |
| simplify-result-layout | AC-001 | 未検証 | タスク3.6: Ubuntu 24.04 LTS・Windows 11で固定保存先のJSON・PNG、直接読戻し、完了表示を確認する。 |
| simplify-result-layout | AC-002 | 未検証 | タスク3.6: 両OSで全件・単独再検査、設定外グループの整理、他グループの保全を確認する。 |
| simplify-result-layout | AC-003 | 未検証 | タスク3.6: 両OSで公開前失敗と公開途中の強制終了を起こし、現行方式での再実行と全件再検査を確認する。 |
| simplify-result-layout | AC-004 | 未検証 | タスク3.6: 両OSで結果親・対象のシンボリックリンク拒否と管理外ファイルの不変を確認する。 |
| simplify-result-layout | AC-005 | 未検証 | タスク3.6: 両OSで準備・学習・検査を全再実行し、新結果の読戻しと管理外ファイルの不変を確認する。 |
| fix-review-findings | AC-001 | 未検証 | タスク6.3: Ubuntu 24.04 LTSとWindows 11で補正省略・明記時の準備画素と指紋を確認する。 |
| fix-review-findings | AC-002 | 未検証 | タスク6.3: 両OSで学習後のcheckpointと最良試行にある擬似異常設定を読み戻す。 |
| fix-review-findings | AC-003 | 未検証 | タスク6.3: 両OSで検査結果の公開前・公開途中の失敗と再実行を確認する。 |
| fix-review-findings | AC-004 | 未検証 | タスク6.3: Windows 11でOptuna接続終了後の履歴移動と読戻しを確認する。 |
| fix-review-findings | AC-005 | 未検証 | タスク6.3: 両OSで5コマンド開始時に全グループの対象一時領域が消えることを確認する。 |
| fix-review-findings | AC-007 | 未検証 | タスク6.3: 両OSで成果物・閾値の混在時に検査結果が公開されないことを確認する。 |

`show-test-progress-and-update-backbone` のAC-003にある`racm_in1k`確認は当時の未検証事項であり、現在の運用には適用しない。<br />
現在の学習は`wide_resnet50_2.tv_in1k`とグループ別の新形式設定から開始する。<br />
上表は対象環境で未検証の受け入れ確認を追跡する。<br />
破壊的変更後は準備・学習・検査をすべて再実行する。

`comparable-heatmap-scale` の実機確認時は、[アーカイブ済みchangeの検証記録](openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md)にモデル確認方法、使用範囲、結果画像・JSON、実行コマンド、環境、日付、制約を追記する。<br />
AC-001〜AC-004 は未検証であり、自動試験の成功やアーカイブは運用開始の承認を意味しない。

タスク4.3〜4.5の実行時は各条件で別の出力先を使い、OS・Python・依存版、GPU無効化方法、5 CLIの結果、成果物の読戻し、実測デバイスを change 内の `evidence/acceptance.md` へ記録する。<br />
現時点では実機確認と運用受け入れは完了していない。

`fix-anomalib-training-checkpoint` のタスク3.1〜3.4では、Ubuntu 24.04 LTSで学習から検査まで実行し、条件・結果を[アーカイブ済みchangeの検証記録](openspec/changes/archive/2026-10-07-fix-anomalib-training-checkpoint/evidence/acceptance.md)へ記録する。<br />
自動試験は成功しているが、対象OSでの一連の実行結果は未検証であり、運用開始の承認を意味しない。
