## ADDED Requirements

### Requirement: REQ-030 グループ別の初期ランダム探索試行数

システムは、運用者が対象グループの `group_detail["<id>"].optuna_settings.sampler.startup_trials` に 0 以上の整数を指定して学習を開始したとき、その値を TPESampler の初期ランダム探索試行数として使用しなければならない(MUST)。<br />
この項目を省略した場合は 5 を使用しなければならない(MUST)。<br />
`startup_trials` が `execution.trials` 以上なら、合計試行回数内で TPE による探索は行われない。

#### Scenario: REQ-030-S01 指定した初期試行数を使用する

- **GIVEN** 対象グループの `sampler.startup_trials` が 0 以上の整数で、学習に必要な準備結果がある
- **WHEN** 運用者が対象グループの学習を実行する
- **THEN** システムは指定値を初期ランダム探索試行数として学習条件を探索する
- **AND** 合計試行回数と MedianPruner の warmup 条件は変更しない

#### Scenario: REQ-030-S02 省略時の初期試行数を使用する

- **GIVEN** 対象グループの `sampler.startup_trials` が省略され、学習に必要な準備結果がある
- **WHEN** 運用者が対象グループの学習を実行する
- **THEN** システムは 5 を初期ランダム探索試行数として学習条件を探索する

#### Scenario: REQ-030-S03 合計試行回数以上を指定する

- **GIVEN** 対象グループの `sampler.startup_trials` が `execution.trials` 以上の 0 以上の整数である
- **WHEN** 運用者が対象グループの学習を実行する
- **THEN** システムは設定された合計試行回数を実行し、その範囲内では TPE による探索を行わない

### Requirement: REQ-031 初期試行数の入力不備の拒否

システムは、対象グループの `sampler.startup_trials` が負数または整数でない場合、学習開始前に入力不備として拒否しなければならない(MUST)。

#### Scenario: REQ-031-S01 負数を拒否する

- **GIVEN** 対象グループの `sampler.startup_trials` が負数である
- **WHEN** 運用者が型番設定を読み込んで学習を開始する
- **THEN** システムは対象項目の入力不備を示して探索を開始しない
- **AND** 運用者は値を修正して再実行できる

#### Scenario: REQ-031-S02 整数でない値を拒否する

- **GIVEN** 対象グループの `sampler.startup_trials` が小数、文字列または真偽値である
- **WHEN** 運用者が型番設定を読み込んで学習を開始する
- **THEN** システムは対象項目の入力不備を示して探索を開始しない
- **AND** 運用者は値を修正して再実行できる

## 試験方針

| 要件区分 | 試験層 | 試験パターン | 自動化方針・利用者が確認する結果 |
| --- | --- | --- | --- |
| 機能要件 `REQ-030` | unit / integration | 0、正整数、省略、合計試行回数以上、グループ別設定 | 全 Scenario を自動検証し、探索で使用する初期試行数と既存の MedianPruner 条件を確認する |
| 機能要件 `REQ-031` | unit / integration | 負数、小数、文字列、真偽値、修正後の再実行 | 全 Scenario を自動検証し、設定読み込み時の入力不備と探索未開始を確認する |

処理失敗と未判定は既存の学習・検査契約に従い、この設定項目による新たな状態を追加しない。<br />
新しい権限や外部連携も追加しない。
