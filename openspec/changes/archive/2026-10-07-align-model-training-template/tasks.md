## 1. 設定契約の整合

- [x] 1.1 `config/part_XX.json` の利用者編集を保持し、epochs候補100・200・300、warmup40、試行10、blur無効を仕様差分と照合する。対応: `REQ-005`、`REQ-006`、設計「データ契約と状態」、`TC-001`、`TC-004`。完了条件: 4値が変更されず、JSONとして読み込める。
- [x] 1.2 `src/app/common/config.py` の省略時warmup、試行回数、blur有効状態、および `tests/fixtures/model_config.json` の代表値をひな形と一致させる。対応: `REQ-005`、`REQ-006`、設計「技術判断」、`TC-001`、`TC-002`、`TC-004`。完了条件: 明示値の優先と新しい既定値を確認できる。

## 2. 自動試験と品質確認

- [x] 2.1 `tests/test_config.py` と `tests/test_training.py` にひな形値、省略時の既定値、10試行、blur初期無効と有効化、表示契約、検証時拡張無効を確認する試験を追加・更新する。対応: `REQ-005`、`REQ-006`、設計「試験設計」、`TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`。完了条件: 参照するpytest試験が全て成功する。
- [x] 2.2 `npm run check` と `uv run --locked python scripts/check_openspec_traceability.py --change align-model-training-template --phase implementation` を実行する。対応: `REQ-005`、`REQ-006`、設計「網羅性確認」、`TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`。完了条件: 品質検査と参照試験の収集が成功する。

## 3. 受け入れ確認

- [x] 3.1 開発環境で `TC-001`、`TC-002` を実行し、設定ひな形の探索条件と10試行を `evidence/acceptance.md` に記録する。対応: `AC-001`、設計「受け入れ検証」。完了条件: 状態「検証済み」、残る検証「なし」、対象環境と結果が記録される。
- [x] 3.2 開発環境で `TC-004`、`TC-005` を実行し、blur初期無効と明示的有効化を `evidence/acceptance.md` に記録する。対応: `AC-002`、設計「受け入れ検証」。完了条件: 状態「検証済み」、残る検証「なし」、対象環境と結果が記録される。
- [x] 3.3 ひな形、仕様差分、既存成果物の変更有無を確認し、`evidence/acceptance.md` に記録する。対応: `AC-003`、設計「受け入れ検証」。完了条件: 状態「検証済み」、残る検証「なし」、差分の確認結果が記録される。
- [x] 3.4 `npx --no-install openspec validate align-model-training-template --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change align-model-training-template --phase complete` を実行する。対応: 全AC、設計「網羅性確認」「受け入れ検証」。完了条件: 両検査が成功する。
