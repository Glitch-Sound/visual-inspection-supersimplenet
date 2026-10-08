## 1. checkpoint の事前照合

- [x] 1.1 `src/app/model_evaluation/evaluation.py` の評価入口が、CLIから渡された照合済みメタデータを使い、直接呼出しでは従来どおり読込・照合するようにする。対応: `AC-001`、`AC-002`、設計「処理フロー」「技術判断」、`TC-001`、`TC-002`。完了条件: CLI の読込回数を増やさず、直接呼出しの契約確認を維持する。
- [x] 1.2 `src/app/model_evaluation/cli.py` で predictor の生成前に checkpoint メタデータの読込と設定照合を行い、照合済みデータを評価処理へ渡す。対応: `AC-001`、`AC-002`、設計「処理フロー」「インターフェースと失敗時の結果」、`TC-001`、`TC-002`。完了条件: 欠落・不一致でモデルを構築せず、入力不備として終了する。

## 2. 検証

- [x] 2.1 `tests/test_evaluation.py` に `TC-001` と `TC-002` の pytest CLIテストを追加し、既存CLIテストの前提を事前照合に合わせる。対応: `AC-001`、`AC-002`、設計「試験設計」、`TC-001`、`TC-002`。完了条件: `tests/test_evaluation.py::test_test_cli_rejects_checkpoint_contract_before_model_construction`、`tests/test_evaluation.py::test_test_cli_validates_checkpoint_before_model_construction` と評価テスト全体が成功する。
- [x] 2.2 `npm run check`、`npx --no-install openspec validate validate-checkpoint-before-model-load --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change validate-checkpoint-before-model-load --phase complete` を実行し、`AC-001` と `AC-002` の結果、日付、環境、制約を `evidence/acceptance.md` と design の「受け入れ検証」に記録する。対応: `AC-001`、`AC-002`、設計「受け入れ検証」、`TC-001`、`TC-002`。完了条件: 各条件が検証済みで残る検証がなく、品質検査と厳密検証が成功する。
