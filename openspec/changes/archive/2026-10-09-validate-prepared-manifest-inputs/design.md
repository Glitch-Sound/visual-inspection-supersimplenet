## 背景・前提

`PreparedSource` は元画像参照とID重複を調べるが、画像名とIDの一致は調べない。<br />
`train` と `evaluate_model` は準備済みmanifestを読み、その参照画像を使用する。<br />
`train --restart` は入力確認より先に旧成果物を削除する。<br />
分割画像名は画像準備で `<元画像stem>_<IDを2桁ゼロ埋め><拡張子>` として生成される。

## 目標・対象外

### 目標

- 学習と検査の共通入力契約で、ID・画像名・設定済み範囲を照合する。
- 準備領域のmanifest、分割画像、またはその親ディレクトリがリンクなら、読込前に拒否する。
- 不正入力では学習・推論・再学習による削除を行わない。

### 対象外

- 画像準備での命名方式、欠落画像の既存の扱い、他の入力領域のリンク方針。

## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-004 | 処理フロー、技術判断 | 学習入力 | 1.1, 1.2, 2.1, 2.5 | TC-001, TC-002, TC-003, TC-007, TC-011 | 不正manifestの拒否と正常入力をpytestで確認 |
| REQ-012 | 処理フロー、技術判断 | 検査入力 | 1.1, 1.3, 2.2 | TC-004, TC-005, TC-006, TC-008, TC-009, TC-010 | 不正manifestの拒否と正常入力をpytestで確認 |

## 業務フローと責務

### 責務一覧

| 責務 / 境界 | 変更種別 | 入力 | 出力・副作用 | 依存先 | 実装候補・確定状況 |
| --- | --- | --- | --- | --- | --- |
| manifest構造 | 変更 | 元画像、ID、画像名 | 不一致なら契約エラー | 画像準備の命名規則 | `common/contracts.py` に確定。両能力が同じ契約を使用するため |
| 準備済み入力の照合 | 追加 | 準備領域、設定済みID | 有効なmanifest、または理由付き入力エラー | manifest構造 | `common/` の共有契約に確定。学習・検査双方から使用するため |
| 学習入力境界 | 変更 | 型番設定、準備領域 | 照合後だけ学習または再学習 | 共通照合 | `model_training/cli.py` に確定 |
| 検査入力境界 | 変更 | 型番設定、準備領域 | 照合後だけ再検査削除・モデル構築・推論と結果保存 | 共通照合 | `model_evaluation/cli.py` と `model_evaluation/evaluation.py` に確定 |

### 処理フロー

1. 両能力は型番設定と準備領域を決定する。
2. 準備領域のパス要素とmanifestのリンクを確認してからmanifestを読む。
3. manifest内の型番、各IDの設定への所属、分割画像名、参照画像のリンクを確認する。ブラックリストや準備失敗による分割欠落は従来どおり許容する。
4. 有効なら学習は必要に応じて旧探索成果物を削除し、集合を分離して学習する。検査は必要に応じて旧結果を削除し、推論と結果保存を行う。
5. 不正なら理由を示して終了し、運用者が準備データを修正・再生成する。

### データ契約と状態

保存形式は変更しない。`split_id` は型番設定のrangeに存在し、`image` は元画像名のstem、ID、拡張子から生成した名前と完全一致する。<br />
manifestと分割画像は通常ファイルを許容し、リンクを拒否する。欠落分割画像の扱いは従来どおりとする。

### インターフェースと失敗時の結果

| 境界 / 操作 | 呼び出し元 → 呼び出し先 | 入力 | 成功結果 | 失敗条件 → 結果 | 冪等性・再試行・タイムアウト |
| --- | --- | --- | --- | --- | --- |
| `train --model` | 運用者 → 学習CLI | 型番と準備済み入力 | 既存の学習結果 | 不正ID・画像名・リンク → 理由付き終了コード2、旧成果物保持 | 入力再生成後に再実行 |
| `test --model` | 運用者 → 検査CLI | 型番と準備済み入力 | 既存の検査結果 | 不正ID・画像名・リンク → 理由付き終了コード2、旧結果保持 | 入力再生成後に再実行 |

## 技術判断

### 判断: 両能力の入力照合を共通化する

- **状態**: 確定。
- **採用内容**: Pydanticのmanifest契約で名前対応を検証し、共通の読込関数で設定済みIDとリンクを検証する。
- **根拠**: 両能力で同じ準備済み形式を使い、検証漏れを防げる。
- **代替案**: 各CLIで個別に照合すると規則が分岐するため採用しない。
- **実装規則 / 不変条件**: 全件を検証してから学習・推論・結果ステージング・再学習削除へ進む。リンク先を読まない。
- **影響**: 不正な既存manifestは再生成が必要。正常入力の形式は維持する。

## 境界条件と失敗モード

| 事象 / 境界条件 | 検知する責務 | 処理・状態変更 | 利用者 / 呼び出し元への結果 | 記録・監視 | 復旧 |
| --- | --- | --- | --- | --- | --- |
| 設定外ID、画像名不一致 | 共通照合 | 再学習・再検査による削除なし | 不正項目を表示し終了コード2 | 既存実行記録 | 準備データを再生成 |
| manifest・画像・親領域のリンク | 共通照合 | リンク先未読込、再学習・再検査による削除なし | パスと理由を表示し終了コード2 | 既存実行記録 | 実ファイルに置換して再実行 |
| 分割画像の欠落 | 学習・検査の既存処理 | 既存のエラーまたは未判定 | 既存の結果 | 既存実行記録 | 画像準備を再実行 |

## セキュリティ・性能・運用

| 観点 | 設計上の対応 | 判定基準 / 監視方法 |
| --- | --- | --- |
| 入力安全性 | 処理前にパス要素のリンクを調べる | リンク先にアクセスしないテストで確認 |
| 運用 | 理由付き入力不備を返す | CLI終了コードと記録を確認 |

処理中に別プロセスがファイルを差し替える競合は、この変更の対象外とする。準備領域を信頼できる運用者だけが更新する既存の運用前提を維持する。
中断済みの学習成果物がある場合は、既存の復旧処理を入力照合より先に実行する。

## 移行とロールバック

保存形式は変えないため移行は不要。拒否された不正manifestは画像準備を再実行する。<br />
ロールバックはコードと差分仕様を戻す。

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 | 検証範囲 | 残る検証 | 証跡 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-004 | REQ-004-S03 | integration | 設定外ID・画像名不一致で学習 | 理由付きで学習前に拒否 | `tests/test_training.py::test_train_rejects_invalid_prepared_manifest` | はい | CLIと契約 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-002 | REQ-004 | REQ-004-S03 | integration | manifest・画像・親領域がリンクで学習 | リンク先未読込、旧成果物保持 | `tests/test_training.py::test_train_rejects_symlinked_prepared_input` | はい | CLIとファイル境界 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-003 | REQ-004 | REQ-004-S01 | unit | 正常なmanifestで集合分離 | 従来の分離結果 | `tests/test_training.py::test_split_groups_by_source_image` | はい | 共通契約と分離 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-004 | REQ-012 | REQ-012-S04 | integration | 設定外ID・画像名不一致で検査 | 推論前に拒否、旧結果保持 | `tests/test_evaluation.py::test_evaluation_rejects_invalid_manifest_before_prediction` | はい | 評価入口 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-005 | REQ-012 | REQ-012-S04 | integration | manifest・画像・親領域がリンクで検査 | リンク先未読込、旧結果保持 | `tests/test_evaluation.py::test_evaluation_rejects_symlinked_prepared_input` | はい | 評価入口とファイル境界 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-006 | REQ-012 | REQ-012-S01 | integration | 正常入力で検査 | 従来の結果保存 | `tests/test_evaluation.py::test_evaluation_records_normal_split` | はい | 評価処理 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-007 | REQ-004 | REQ-004-S02 | unit | 元画像不足で集合分離 | 必要数を示して拒否 | `tests/test_training.py::test_split_rejects_insufficient_source_images` | はい | 集合分離 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-008 | REQ-012 | REQ-012-S02 | unit | 不正な結果契約を読み戻す | 理由付きで拒否 | `tests/test_results.py::test_result_contract_rejects_invalid_score_and_runtime` | はい | 結果契約 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-009 | REQ-012 | REQ-012-S03 | integration | 同stem異拡張子を検査 | 結果を区別して保存 | `tests/test_evaluation.py::test_evaluation_keeps_same_stem_different_extensions` | はい | 評価処理 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-010 | REQ-012 | REQ-012-S04 | integration | 画像名不一致またはmanifestリンクで `test --restart` | 旧結果を保持し、モデルを構築しない | `tests/test_evaluation.py::test_test_cli_restart_preserves_results_for_invalid_manifest` | はい | CLIの再検査境界 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| TC-011 | REQ-004 | REQ-004-S01 | integration | 実ファイル付き正常manifestで `train` CLI を実行 | 分離済み画像を探索へ渡し、CLIが成功する | `tests/test_training.py::test_train_cli_accepts_valid_prepared_images` | はい | CLIと探索への引き渡しをテストダブルで確認 | なし | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |

## 網羅性確認

| 要件ID | Scenario数 | 対応TC数 | 未対応Scenario | 状態 |
| --- | --- | --- | --- | --- |
| REQ-004 | 3 | 5 | なし | 設計済み |
| REQ-012 | 4 | 6 | なし | 設計済み |

## 受け入れ検証

| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 両CLIの設定外ID・画像名不一致 | TC-001、TC-004 | なし | 検証済み | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| AC-002 | 両CLIのmanifest・画像・親領域リンク | TC-002、TC-005 | なし | 検証済み | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
| AC-003 | 実ファイルを持つ正常入力のCLI引き渡しと品質検査 | TC-003、TC-006、TC-011、`npm run check` | なし | 検証済み | `openspec/changes/archive/2026-10-09-validate-prepared-manifest-inputs/evidence/acceptance.md` |
