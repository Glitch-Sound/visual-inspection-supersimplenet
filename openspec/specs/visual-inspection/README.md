# 外観検査仕様ガイド

このディレクトリは、外観検査ワークフローの正式仕様を3つのcapabilityに分けて管理します。本書は各仕様の関係を示す非規範的な案内文書です。システムが満たす要件とScenarioは、各capabilityの`spec.md`を正本とします。

## OpenSpec上の位置付け

OpenSpecでは、`openspec/specs/<capability-path>/spec.md`が1つのcapabilityを表します。したがって、`visual-inspection/`は子仕様を束ねる名前空間であり、`visual-inspection/spec.md`という親仕様が自動生成される構造ではありません。

現在登録しているcapabilityは次の3つです。

| Capability | 正式仕様 | 提供する能力 |
| --- | --- | --- |
| `visual-inspection/image-preparation` | [画像準備仕様](image-preparation/spec.md) | 元画像を位置合わせ・分割し、学習・検査で使用できる追跡可能な入力を準備する |
| `visual-inspection/model-training` | [モデル学習仕様](model-training/spec.md) | 正常画像中心のデータから、型番別モデル、探索結果、暫定閾値を再現可能に生成・再開する |
| `visual-inspection/model-evaluation` | [モデル評価仕様](model-evaluation/spec.md) | モデルを使って分割画像と元画像を判定し、可視化、未判定、実行環境を含む結果を保存する |

`visual-inspection/spec.md`を追加した場合、それは3仕様の目次ではなく、`visual-inspection`という第4のcapabilityとして扱われます。現在の横断要件は既存のcapabilityに配置しており、独立した要件群が必要になった場合に新しいcapabilityを検討します。

## 3つに分割する理由

3仕様は処理順だけでなく、主な責務、成果物、検証対象が異なります。導入時には、1つの`visual-inspection` changeで3つのcapabilityとして定義されました。

| 観点 | 画像準備 | モデル学習 | モデル評価 |
| --- | --- | --- | --- |
| 主な入力 | 基準画像、学習・試験元画像、分割・位置合わせ設定 | 学習準備manifestと分割画像、探索・拡張設定 | 試験準備manifestと分割画像、モデル、閾値 |
| 主な出力 | 確認画像、分割画像、準備manifest、未判定引き継ぎ情報 | checkpoint、Optuna study、最良試行、暫定閾値 | 分割結果画像、元画像単位の結果JSON |
| 主な関心 | 入力の再現性と追跡可能性 | 学習条件、再現性、モデルと閾値の整合性 | スコア、判定集約、可視化、結果契約 |
| 対応CLI | `check`、`train-pre`、`test-pre` | `train` | `test` |

この境界により、例えば位置合わせ・分割の変更を、探索方法や結果JSONの変更と分離して検討できます。また、学習と検査で同じ画像準備能力を共有しつつ、モデル生成と判定結果の責務を混在させずに要件とScenarioを管理できます。

複数の処理に関わる要件もあります。例えば、GPUからCPUへの切り替えと実行環境の記録は学習・検査の両方に適用され、現在は[モデル評価仕様](model-evaluation/spec.md)の`REQ-009`と`NREQ-001`で管理しています。

## 仕様間の関係

```text
+---------------------------+
| image-preparation         |
|                           |
| check                     |
| train-pre                 |
| test-pre                  |
+-------------+-------------+
              |
              +-------------------------------+
              |                               |
              v                               v
+-------------+-------------+   +-------------+-------------+
| model-training            |   | prepared test images      |
|                           |   | and manifest              |
| train                     |   +-------------+-------------+
+-------------+-------------+                 |
              |                               |
              | model and threshold           |
              +---------------+---------------+
                              |
                              v
                +-------------+-------------+
                | model-evaluation          |
                |                           |
                | test                      |
                +-------------+-------------+
                              |
                              v
                split results and source-image results
```

画像準備は、学習と評価の両方に入力を提供します。モデル評価は、モデル学習が生成したcheckpoint・探索結果・暫定閾値と、画像準備が生成した試験manifest・分割画像の両方を使用します。

## 要件の配置基準

新しい要件は、主な観測結果と責務に基づいて配置します。複数の処理に関わる場合は、既存の横断要件も確認します。

- 元画像から学習・検査入力を作るまでの要件は、`image-preparation`へ配置する。
- 学習データの構成、探索、データ拡張、モデル・閾値の生成と再開は、`model-training`へ配置する。
- 推論、可視化、判定集約、検査結果、再検査は、`model-evaluation`へ配置する。
- 複数仕様に影響する変更でも、同じ要件を重複して記載しない。主な責務を持つcapabilityへ要件を置き、必要に応じて他仕様の入力・出力契約との関係を明記する。
- 既存3仕様に属さない独立した横断能力が必要になった場合は、新しいcapabilityとして定義するかをOpenSpec changeで検討する。

## 全体フローと履歴

利用時のコマンド、入力配置、成果物、終了コードは、リポジトリの[README](../../../README.md)を参照してください。

3つのcapabilityは、`visual-inspection` changeで同時に導入されました。導入時の背景、利用者・運用者、変更後の業務フロー、対象範囲は、アーカイブ済みの[proposal](../../changes/archive/2026-10-03-visual-inspection/proposal.md)に記録されています。以後の規範的な振る舞いは、アーカイブ履歴ではなく各正式仕様を参照してください。
