## 背景・前提

`src/app/common/model_adapter.py`のモデル生成関数を学習と検査が共用する。現行の重み指定は`wide_resnet50_2.tv_in1k`であり、`train --restart`は対象型番のOptuna探索領域とcheckpointを削除する。checkpointの独自メタデータには重み識別子がないため、移行時には全型番を再学習し、旧checkpointで`test`しない。<br />
`test`は`src/app/model_evaluation/evaluation.py`で試験manifestの元画像を順に処理する。`train-pre`と`test-pre`には端末ならバー、それ以外なら標準エラーへ件数を出す進捗表示がある。結果JSONは標準出力へ一件出る。

## 目標・対象外

### 目標

- `test`が元画像の処理済み件数と総件数を端末・非端末で表示し、個別エラーと全体失敗を区別する。
- 学習と検査のモデル生成で`wide_resnet50_2.racm_in1k`を使い、再学習手順を明記する。

### 対象外

- バックボーン選択の設定化。今回は一種類に固定する。
- ImageNet分類精度から異常検出性能を推定して保証すること。
- 旧checkpointを新バックボーンの成果物として自動変換すること。全型番の再学習を採用したため。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-020 | 技術判断、移行とロールバック | 共通モデル生成、学習成果物、運用 | 1.1, 1.2, 3.1, 4.3, 4.4 | TC-001, TC-002 | 重み識別子と再学習契約の自動試験、対象OSでの実学習 |
| NREQ-003 | 業務フローと責務、インターフェースと失敗時の結果 | 検査ループ、CLI表示 | 2.1, 2.2, 3.2, 4.1, 4.2 | TC-003, TC-004, TC-005, TC-006 | 進捗コールバックとCLIの自動試験、対象OSの端末確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| モデル生成 | 変更 | 特徴層、画像サイズ、学習率倍率 | 新重みの特徴抽出器 | timm、Anomalib | `common/model_adapter.py`の固定名変更に確定。既存の共有入口で両能力へ適用できる |
| 検査進捗通知 | 追加 | 処理済み元画像数、総数 | コールバック通知 | 試験manifest | `model_evaluation/evaluation.py`の元画像ループに確定 |
| 検査進捗表示 | 追加 | 通知された件数 | 標準エラーのバーまたは行 | Rich、CLI | `model_evaluation/cli.py`に確定。既存準備表示の振る舞いを参照し、能力固有の表示とする |
| 再学習と再検査 | 変更 | 対象型番、旧成果物 | 新checkpoint、閾値、検査結果 | `train --restart`、`test --restart` | READMEの運用手順に確定 |

### 処理フロー

1. 運用者は版更新後に型番ごとの`train --restart`を実行する。新しいバックボーン重みを読み、旧探索履歴とcheckpointを置き換える。
2. 運用者は学習した暫定閾値と異常マップ値に合わせて`inspection_threshold`と`heatmap_range`を確認する。旧検査結果を`test --restart`で再生成する。
3. `test`はcheckpointと設定を照合し、試験manifestを読み込む。妥当な入力があれば進捗を`0/N`で開始する。
4. 各元画像について全分割の推論、個別エラーの記録、元画像判定の集約を終えた後に件数を一件進める。未判定も処理済みに含む。
5. 全件処理と結果保存が完了したら従来の終了表示と標準出力JSON一件を出す。途中で全体失敗した場合は進捗をそれ以上進めず、既存のエラー終了に従う。

### データ契約と状態

| データ / 契約 | 変更 | フィールド・型・必須性 | 制約・既定値 | 生成・更新主体 | 互換性 / 移行 |
| --- | --- | --- | --- | --- | --- |
| 進捗通知 | 追加 | `processed: int`, `total: int` | `0 <= processed <= total`。元画像単位 | 検査処理 | 保存しない。標準エラーにだけ反映 |
| checkpoint・探索結果 | 形式変更なし | 既存の状態・メタデータ | 旧重みの成果物は使用しない | 学習処理 | `train --restart`で対象型番ごとに置換 |
| 検査結果JSON・標準出力JSON | 変更なし | 既存の必須項目 | 進捗は混入させない | 検査処理・CLI | `test --restart`で旧結果を置換 |

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train --restart` | 運用者 → 学習CLI | 対象型番 | 新モデルと暫定閾値 | 重み取得・学習失敗 → 既存エラー表示。旧モデルを新重みと見なさない | 原因解消後に再実行 |
| `test` | 運用者 → 検査CLI | 対象型番 | 標準エラーへ進捗、標準出力へJSON一件 | 入力不備 → 既存の入力不備終了。全体失敗 → 部分進捗で停止して失敗表示 | 修正後に`test --restart` |
| 進捗通知 | 検査処理 → CLI表示 | 件数 | バーまたは行を更新 | 個別分割エラー → 元画像判定後に一件進める | 該当なし |

## 技術判断

### 判断・候補: 元画像単位の進捗

- **状態**: 確定。
- **採用内容**: `evaluate_model`に任意の進捗コールバックを追加し、manifest読込後の`0/N`と元画像集約後の件数を通知する。CLI側で端末判定に応じてRichバーまたは行を標準エラーへ表示する。
- **根拠**: 既存の画像準備CLIと同じ数え方を使え、分割数が画像ごとに違っても件数が理解しやすい。
- **代替案**: 分割画像単位のバーは元画像判定の進行と一致しないため採用しない。
- **実装規則 / 不変条件**: 標準出力JSONと終了コードは不変。未判定や個別エラーも判定集約後に一件。全体失敗では未処理分を進めない。
- **影響**: `evaluation.py`、検査CLI、関連テスト。

### 判断・候補: バックボーン固定名の変更

- **状態**: 確定。
- **採用内容**: 共有モデル生成の重み名を`wide_resnet50_2.racm_in1k`へ変更し、全型番で明示的な再学習を行う。
- **根拠**: 利用者が直接切り替えと旧成果物破棄を選択した。現行の学習・検査は同じモデル生成入口を使用する。
- **代替案**: 設定化や旧重みとの並行運用は今回不要。
- **実装規則 / 不変条件**: 前処理、特徴層探索、スコア契約、判定規則は維持する。旧checkpointを新モデルと扱わず、旧探索履歴を再利用しない。Anomalibは現重みの動作を検証済みと明記しているため、新重みでの実学習・推論を別途確認する。
- **影響**: `common/model_adapter.py`、README、学習テスト、実機確認。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 試験manifestが空 | 検査処理 | `0/0`を表示し、結果は0件 | 完了件数0を確認できる | CLI表示 | 必要なら試験準備を再実行 |
| 分割推論の個別失敗 | 検査処理 | 分割エラーを結果に保持し、元画像集約後に進捗を一件進める | エラーと処理済み件数 | 実行記録 | 原因修正後に再検査 |
| 全体失敗 | CLI共通実行部 | 進捗は最後の確定件数のまま停止 | 失敗理由・終了コード | 実行記録 | 原因修正後に再実行 |
| 新重みの取得失敗 | モデル生成 | 学習を完了しない | 既存の処理失敗 | 実行記録 | 接続・キャッシュ確認後に`train --restart` |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| セキュリティ | 新たな権限・外部接続は追加しない。事前学習重み取得は既存経路を使用 | 既存の入力検証と保存先制限を維持 |
| 性能 | 元画像一件につき一度進捗通知する。入力サイズと探索条件は維持 | 対象環境で学習・検査が完了すること。数値目標は本番評価で決める |
| 運用 | 全型番の再学習と再検査の順序をREADMEに記載 | 旧学習成果物を利用せず、閾値・表示範囲を確認する |

## 移行とロールバック

1. 版更新後、対象の全型番で`train --model <型番> --restart`を実行する。旧探索履歴とcheckpointは保持しない。
2. 新しい暫定閾値を確認し、検査用閾値とヒートマップ表示範囲を見直す。`test --model <型番> --restart`で旧検査結果を置き換える。
3. 実重みの取得・学習・検査が失敗した場合は原因を修正して再学習する。旧モデルを利用するロールバックは想定しない。元画像と準備済み画像は維持する。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-020 | REQ-020-S01 | unit / integration | モデル生成を捕捉し、新重み名で特徴抽出器を構築 | 指定名が渡り、導入済みAnomalibが特徴抽出器を構築できる | `tests/test_training.py::test_model_adapter_uses_racm_backbone` | はい | ローカル依存・重みダウンロードなし | 実重み学習とcheckpoint検査 (4.3) | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| TC-002 | REQ-020 | REQ-020-S02 | integration | 旧探索領域とcheckpointがある状態で再学習準備を実行 | 旧成果物を削除して新規探索する | `tests/test_training.py::test_training_restart_replaces_only_derived_artifacts` | はい | 既存の成果物削除契約 | 対象OSの全型番再学習 (4.4) | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| TC-003 | NREQ-003 | NREQ-003-S01 | unit | 標準エラーを端末として進捗を更新 | バーが初期値と完了値を受ける | `tests/test_runtime.py::test_evaluation_progress_uses_bar_on_terminal` | はい | Rich表示のテストダブル | 対象OSの端末表示 (4.1) | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| TC-004 | NREQ-003 | NREQ-003-S02 | integration | 非端末で複数元画像を検査 | `0/N`から`N/N`まで標準エラー、標準出力JSON一件 | `tests/test_runtime.py::test_test_cli_reports_source_progress_non_tty` | はい | CLIと進捗通知の結合 | 対象OSのCLI表示 (4.1) | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| TC-005 | NREQ-003 | NREQ-003-S03 | integration | 未判定と個別分割エラーを含むmanifestで検査 | 集約済み元画像だけ件数が進む | `tests/test_evaluation.py::test_evaluation_progress_counts_undetermined_and_split_errors` | はい | 固定画像・予測ダブル | 対象OSの実画像 (4.2) | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| TC-006 | NREQ-003 | NREQ-003-S04 | integration | 二件目の元画像で全体失敗を発生 | 一件目までの進捗、既存の失敗終了 | `tests/test_evaluation.py::test_evaluation_progress_stops_on_fatal_failure` | はい | 結果保存前の失敗境界 | 対象OSのCLI表示 (4.2) | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-020 | 2 | 2 | なし | 網羅 |
| NREQ-003 | 4 | 4 | なし | 網羅 |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 端末・非端末の複数元画像、標準出力JSON | TC-003, TC-004と対象OSのCLI確認 | 対象OSの端末表示 (4.1) | 未検証 | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| AC-002 | 未判定・個別エラー・全体失敗 | TC-005, TC-006と対象OSのCLI確認 | 対象OSの実画像確認 (4.2) | 未検証 | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| AC-003 | 新バックボーンでの学習とcheckpoint検査 | TC-001と対象OSでの実学習・検査 | 実重み取得・学習・検査 (4.3) | 未検証 | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
| AC-004 | 全型番の旧成果物破棄と再学習手順 | TC-002、README手順確認、対象環境での再実行 | 全型番の運用実施 (4.4) | 未検証 | `openspec/changes/show-test-progress-and-update-backbone/verification.md` |
