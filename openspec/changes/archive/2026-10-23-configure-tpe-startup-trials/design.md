## 背景・前提

`SamplerSettings` は現在 `name` と `seed` を持ち、`create_study` は `TPESampler` に seed だけを渡す。<br />
同名の `startup_trials` は `PrunerSettings` に既にあり、`MedianPruner` の `n_startup_trials` に渡される。<br />
今回の sampler 設定と pruner 設定は独立させる。<br />
型番設定は `src/app/common/config.py` の Pydantic モデルで検証し、探索は `src/app/model_training/search.py` が開始する。<br />
`README.md` は既に破壊的変更後の `check`、`train-pre`、`train`、`test-pre`、`test` の再実行順を案内している。

## 目標・対象外

### 目標

- `sampler.startup_trials` を 0 以上の厳密な整数として受け取り、省略時は 5 にする。
- 値を `TPESampler(n_startup_trials=...)` に渡し、MedianPruner の設定を変えない。
- ひな形と README に設定値、TPE が働く条件、再実行手順を示す。

### 対象外

- `pruner.startup_trials`、合計試行回数、探索範囲の変更。
- 既存成果物の移行・互換処理。<br />
  全工程を再実行する前提である。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-030 | データ契約と状態、処理フロー、技術判断 | 型番設定 → 学習探索 | 1.1、1.2、1.3、2.1 | TC-001、TC-002、TC-003 | 設定読込、Optuna への引数、試行数、既存 pruner 条件を自動確認 |
| REQ-031 | インターフェースと失敗時の結果、境界条件と失敗モード | 型番設定 → 学習 CLI | 1.1、2.2 | TC-004、TC-005 | 不正値の検証エラー、探索未開始、修正後の読込を自動確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| 型番設定の検証 | 変更 | `sampler.startup_trials` | 非負整数または入力不備 | 既存の設定読込 | `src/app/common/config.py` に確定。<br />既存 `SamplerSettings` の責務 |
| 学習条件探索 | 変更 | 検証済み sampler 設定 | 指定初期試行数の探索 | Optuna | `src/app/model_training/search.py` に確定。<br />既存 `create_study` の責務 |
| 設定案内 | 変更 | 既定値と運用条件 | ひな形と説明 | 運用者 | `config/part_XX.json` と `README.md` に確定 |

### 処理フロー

1. 運用者が型番設定を用意し、学習 CLI を起動する。<br />
   設定読込は sampler の `startup_trials` を検証し、省略なら 5 を補う。
2. 設定が不正なら既存の入力不備経路で探索前に終了する。<br />
   運用者は値を修正して再実行する。
3. 学習探索は検証済み値を sampler に渡す。<br />
   pruner には従来の `pruner.startup_trials` などを渡し、合計試行回数を変更しない。
4. 運用者は設定変更後に既存の手順に従い、準備・学習・検査を再実行して成果物を確認する。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 型番設定の `optuna_settings.sampler` | 追加 | `startup_trials`: 整数、任意 | 0 以上、省略時 5。<br />小数・文字列・真偽値を拒否 | 運用者、設定読込 | 旧成果物は移行しない。<br />旧設定での項目省略は 5 として読める |
| `optuna_settings.pruner` | 変更なし | 既存の `startup_trials` など | 既存値を保持 | 運用者 | REQ-005-S01 を保持 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| 型番設定の読込 | 学習 CLI → 設定読込 | 任意の非負整数 | 検証済み設定 | 負数・非整数 → 既存の入力不備表示と終了、探索未開始 | 値を修正して再実行。<br />タイムアウトなし |
| 探索の作成 | 学習 CLI → 学習探索 | 検証済み設定 | 指定値の sampler と既存 pruner | 既存の探索失敗経路に従う | 既存の新規探索手順で再実行 |

## 技術判断

### 判断・候補: sampler と pruner の同名設定を分離する

- **状態**: 確定。
- **採用内容 / 候補**: `SamplerSettings.startup_trials` に `Annotated[StrictInt, Field(ge=0)] = 5` を追加し、`TPESampler` の `n_startup_trials` に渡す。
- **根拠**: `int` だけでは Pydantic による小数・文字列・真偽値からの変換を許す可能性がある。<br />
  既存の `StrictInt` を使い、要求された整数だけを受け入れる。
- **代替案**: 既存の `pruner.startup_trials` を流用する案は sampler と pruner の独立設定を失うため採用しない。
- **実装規則 / 不変条件**: `PrunerSettings` と `MedianPruner` の引数、既存 `REQ-005-S01` の文面は変更しない。
- **影響**: `src/app/common/config.py` と `src/app/model_training/search.py` のみを実装変更する。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| `startup_trials = 0` | 設定読込 | 有効として保持 | 学習を開始できる | 既存の学習記録 | 不要 |
| `startup_trials >= execution.trials` | 運用者の設定判断 | 有効として保持。<br />TPE 探索の試行はない | README で関係を確認できる | 既存の試行履歴 | TPE を使うなら値を合計試行回数未満に変更して再実行 |
| 負数・小数・文字列・真偽値 | 設定読込 | 探索・成果物更新なし | 対象項目の入力不備 | 既存の CLI エラー | 値を修正して再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力検証 | 非負の厳密な整数として検証する | 不正値は学習前に拒否 |
| 性能 | 合計試行回数は変更せず、新しい性能目標を設定しない | 既存の試行履歴で実行試行数を確認 |
| 運用 | README に既定値、合計試行回数との関係、全工程の再実行を記す | ひな形と README の記述を照合 |

認証・認可、外部サービス、秘密情報の扱いは変更しない。

## 移行とロールバック

1. 実装・設定ひな形を適用し、変更後の設定を用いて `check`、`train-pre`、`train`、`test-pre`、全件 `test` の順に再実行する。<br />
   旧成果物の移行・再利用は行わない。
2. 旧版へ戻す場合は旧版に適合する設定と成果物を用意し、同じ工程を再実行する。<br />
   旧成果物の互換性は保証しない。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-030 | REQ-030-S01 | unit / integration | 0 と正整数をグループ設定へ指定し、設定読込・探索作成 | 指定値を sampler へ渡し、pruner 条件を保持 | `tests/test_training.py::test_req_030_s01_sampler_startup_trials` | はい | ローカルの実 Optuna 作成と引数契約 | 対象 OS の実画像探索、タスク 3.2 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |
| TC-002 | REQ-030 | REQ-030-S02 | unit / integration | sampler の項目を省略して設定読込・探索作成 | 既定値 5 を渡す | `tests/test_training.py::test_req_030_s02_default_startup_trials` | はい | ローカルの実 Optuna 作成と引数契約 | 対象 OS の実画像探索、タスク 3.2 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |
| TC-003 | REQ-030 | REQ-030-S03 | integration | 初期試行数を合計試行回数以上にして探索 | 合計試行回数を維持し TPE の適用前に終わる | `tests/test_training.py::test_req_030_s03_trials_within_startup` | はい | ローカルの実 Optuna による試行数と探索段階 | 対象 OS の実画像探索、タスク 3.2 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |
| TC-004 | REQ-031 | REQ-031-S01 | unit | 負数の設定を読み込む | ValidationError、探索未開始 | `tests/test_config.py::test_req_031_s01_negative_sampler_startup_trials` | はい | ローカルの設定検証 | 対象 OS の CLI 表示、タスク 3.2 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |
| TC-005 | REQ-031 | REQ-031-S02 | unit | 小数・文字列・真偽値で失敗後、整数へ修正して再読込 | 不正値を拒否し、修正後は成功 | `tests/test_config.py::test_req_031_s02_noninteger_sampler_startup_trials` | はい | ローカルの設定検証と再試行 | 対象 OS の CLI 表示、タスク 3.2 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-030 | 3 | 3 | なし | 設計上網羅 |
| REQ-031 | 2 | 2 | なし | 設計上網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 0、正整数、省略、合計試行回数以上の設定 | TC-001〜TC-003 と対象 OS の実画像探索 | 対象 OS の実画像探索、タスク 3.2 | 未検証 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |
| AC-002 | 負数・非整数、修正後の再実行 | TC-004・TC-005 と対象 OS の CLI 入力不備確認 | 対象 OS の CLI 確認、タスク 3.2 | 未検証 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |
| AC-003 | ひな形の値と README の説明 | 設定ひな形の差分と README を照合 | なし | 検証済み | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |
| AC-004 | pruner の warmup と全工程の再実行 | 回帰試験、対象 OS での `check` から `test` までの実行 | 対象 OS の実画像による全工程、タスク 3.2 | 未検証 | `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` |

証跡は実施後に `openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` へ環境、版、日付、コマンド、結果、制約とともに記録する。<br />
対象 OS の実行が利用できない場合は未検証のまま残し、制限付きアーカイブの条件を別途満たす必要がある。
