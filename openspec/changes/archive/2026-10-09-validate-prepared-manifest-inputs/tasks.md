## 1. 準備済み入力の契約と処理境界

- [x] 1.1 `src/app/common/contracts.py` と `src/app/common/paths.py` に、元画像名・IDと分割画像名の照合、設定済みIDの照合、準備領域・manifest・参照画像のリンク拒否を追加する。対応: `REQ-004`、`REQ-012`、`AC-001`、`AC-002`、設計「処理フロー」「技術判断」、`TC-001`、`TC-002`、`TC-004`、`TC-005`。完了条件: 不正入力が理由付きの値エラーになり、リンク先を読まない。
- [x] 1.2 `src/app/model_training/cli.py` で共通入力照合を学習・再学習削除前に呼ぶ。対応: `REQ-004`、`AC-001`、`AC-002`、設計「インターフェースと失敗時の結果」、`TC-001`、`TC-002`。完了条件: 不正入力では学習せず、旧成果物を維持する。
- [x] 1.3 `src/app/model_evaluation/cli.py` と `src/app/model_evaluation/evaluation.py` で共通入力照合を再検査削除・モデル構築・推論・結果ステージング前に呼ぶ。対応: `REQ-012`、`AC-001`、`AC-002`、設計「インターフェースと失敗時の結果」、`TC-004`、`TC-005`、`TC-010`。完了条件: 不正入力ではモデルを構築・推論せず、旧結果を維持する。

## 2. 自動試験と受け入れ確認

- [x] 2.1 `tests/test_training.py` に `TC-001`、`TC-002` の pytest テストを追加し、`TC-003`、`TC-007` の既存pytest試験を確認する。対応: `REQ-004-S01/S02/S03`、`AC-001`、`AC-002`、`AC-003`、設計「試験設計」。完了条件: 不正入力が学習前に拒否され、正常入力の集合分離試験が成功する。
- [x] 2.2 `tests/test_evaluation.py` と `tests/test_results.py` に `TC-004`、`TC-005`、`TC-010` の pytest テストを追加し、`TC-006`、`TC-008`、`TC-009` の既存pytest試験を確認する。対応: `REQ-012-S01/S02/S03/S04`、`AC-001`、`AC-002`、`AC-003`、設計「試験設計」。完了条件: 不正入力が再検査削除・モデル構築・推論前に拒否され、正常結果の試験が成功する。
- [x] 2.3 `npm run check`、`npx --no-install openspec validate validate-prepared-manifest-inputs --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change validate-prepared-manifest-inputs --phase complete` を実行する。対応: `AC-001`、`AC-002`、`AC-003`、設計「受け入れ検証」、`TC-001`〜`TC-010`。完了条件: 全試験と厳密検証、トレーサビリティ検査が成功する。
- [x] 2.4 `AC-001`、`AC-002`、`AC-003` を設計「受け入れ検証」の条件で確認し、`evidence/acceptance.md` に日付・環境・コマンド・結果・制約を記録して設計の状態を更新する。対応: `AC-001`、`AC-002`、`AC-003`、設計「受け入れ検証」、`TC-001`〜`TC-010`。完了条件: 各ACの結果と実在証跡を確認できる。
- [x] 2.5 `tests/test_training.py` に `TC-011` の pytest 試験を追加し、実ファイル付き正常manifestが `train` CLIから元画像単位の集合分離と探索への引き渡しを通過することを確認する。対応: `REQ-004-S01`、`AC-003`、設計「試験設計」、`TC-011`。完了条件: 正常なCLI終了記録と分離済み実ファイルを自動試験で確認できる。
