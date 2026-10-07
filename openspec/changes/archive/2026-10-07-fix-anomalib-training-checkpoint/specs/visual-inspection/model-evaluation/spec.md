## ADDED Requirements

### Requirement: REQ-016 アプリ生成checkpointの契約照合

システムは、アプリが生成したcheckpointを用いて検査を開始する時に、保存された型番、スコア契約および閾値を読み込み、現在の設定と照合しなければならない (MUST)。

#### Scenario: REQ-016-S01 一致するcheckpointで検査する

- **GIVEN** 型番、スコア契約および閾値が設定と一致するアプリ生成checkpointがある
- **WHEN** 運用者が `test --model <型番>` を実行する
- **THEN** 契約照合を通過し、分割画像の検査が実行される

#### Scenario: REQ-016-S02 メタデータのないcheckpointを拒否する

- **GIVEN** 必要なメタデータを持たないcheckpointがある
- **WHEN** 運用者が `test --model <型番>` を実行する
- **THEN** 必要なメタデータがない理由を示して検査開始前にエラー終了する
- **AND** 運用者は正しい学習成果物を用意して再実行できる

## 試験方針

| 要件区分 | 試験層 | 試験パターン | 自動化方針・利用者が確認する結果 |
| --- | --- | --- | --- |
| 機能要件 | unit / integration | メタデータを含むcheckpointの読込、欠落時の拒否 | 各Scenarioをpytestで検証し、Ubuntu実機の検査実行を別途確認する |
