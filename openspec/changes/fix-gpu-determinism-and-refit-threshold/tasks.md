## 1. GPU試行の状態管理

- [x] 1.1 `src/app/model_training/trainer.py` で `synthetic_auroc` の試行ごとにseedを固定し、CUDA非対応の決定論演算をエラーにしない設定を試行範囲に限定して終了時に復元する。対応: `REQ-038`、設計「処理フロー」「GPU決定論設定の範囲」、`TC-001`・`TC-002`。完了条件: 成功・例外の両方で開始前の有効状態と `warn_only` 状態へ戻る。
- [x] 1.2 `tests/test_training.py` の試行実行境界に成功・失敗時の設定復元と次処理の独立性を確認する自動テストを用意する。対応: `REQ-038`、設計「境界条件と失敗モード」、`TC-001`・`TC-002`。完了条件: `test_synthetic_trial_scopes_determinism` と `test_synthetic_trial_restores_determinism_on_failure` が成功する。

## 2. 最終モデルの閾値と保存契約

- [x] 2.1 `src/app/model_training/trainer.py` と `cli.py` で最終checkpointと同じモデルを全正常分割画像へ評価モード・拡張なしで再適用し、従来方式のスコアを成果物公開へ渡す。対応: `REQ-007`・`REQ-035`、設計「処理フロー」「最終checkpointのスコア取得」、`TC-009`・`TC-011`。完了条件: スコア件数が画像数と一致し、欠落・非有限値を公開前に拒否する。
- [x] 2.2 `src/app/model_training/artifacts.py` で従来方式の閾値を最終モデルの評価スコアから算出し、新方式の算出式と既存の3成果物トランザクションを維持する。対応: `REQ-007`・`REQ-035`、設計「データ契約と状態」「閾値根拠と一式公開」、`TC-004`・`TC-010`・`TC-011`。完了条件: checkpoint・型番設定・結果JSONの閾値が一致し、失敗時は旧一式を保持する。
- [x] 2.3 `src/app/common/contracts.py`、`src/app/model_training/artifacts.py`、`src/app/model_evaluation/evaluation.py` に閾値スコアのモデル系統と最終checkpoint参照を追加し、新規結果の方式との整合を推論前に確認する。対応: `REQ-007`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-004`・`TC-007`。完了条件: 従来方式では最終checkpointを特定でき、新方式は交差検証由来と分かり、旧JSONを最終モデル由来と誤認しない。

## 3. 自動試験、文書、受け入れ

- [x] 3.1 `tests/test_training.py` に `TC-001`、`TC-002`、`TC-003` のpytestを実装・実行し、設定復元、例外後の独立性、CPU同seed探索を検証する。対応: `REQ-038`、設計「試験設計」。完了条件: 設計表の3関数と `uv run --locked pytest tests/test_training.py -q` が成功する。
- [x] 3.2 `tests/test_training.py` に `TC-004`、`TC-005`、`TC-006`、`TC-007`、`TC-008`、`TC-009`、`TC-010`、`TC-011`、`TC-012` のpytestを実装または更新し、従来方式の最終スコア、3成果物、モデル識別、異常スコア保全、新方式の不変性を検証する。対応: `REQ-007`・`REQ-035`、設計「試験設計」。完了条件: 設計表の9関数と `uv run --locked pytest tests/test_training.py -q` が成功する。
- [ ] 3.3 CUDA環境で `synthetic_auroc` の探索・交差検証・最終学習を実行し、決定論設定の漏れがないことを確認して `evidence/acceptance.md` に環境・版・seed・結果を記録する。対応: `AC-001`、設計「受け入れ検証」。完了条件: 実CUDAの一連実行結果を確認し、AC-001を「検証済み」にできる。
- [ ] 3.4 対象OSのCPU環境で同一入力・設定・seedの探索を2回実行し、試行条件・目的値・最良試行を比較して `evidence/acceptance.md` に記録する。対応: `AC-002`、設計「受け入れ検証」。完了条件: 対象環境での再現結果を確認し、AC-002を「検証済み」にできる。
- [ ] 3.5 対象環境で従来方式の最終checkpointを評価モード・拡張なしで全正常学習集合に再適用し、保存閾値を再計算して `evidence/acceptance.md` に記録する。対応: `AC-003`、設計「受け入れ検証」。完了条件: 実モデルの再計算値と保存閾値が一致し、AC-003を「検証済み」にできる。
- [ ] 3.6 対象環境でcheckpoint・型番設定・最良試行結果を読み戻し、閾値3件とモデル識別情報を照合して `evidence/acceptance.md` に記録する。対応: `AC-004`、設計「受け入れ検証」。完了条件: 3件の値と最終checkpoint参照が一致し、AC-004を「検証済み」にできる。
- [ ] 3.7 対象環境でスコア異常・学習失敗から再実行までを確認し、旧3成果物の保全と失敗理由を `evidence/acceptance.md` に記録する。対応: `AC-005`、設計「受け入れ検証」。完了条件: 失敗と復旧の結果を確認し、AC-005を「検証済み」にできる。
- [ ] 3.8 対象環境で新方式の交差検証スコアから閾値を再計算し、最終checkpointとの関係を `evidence/acceptance.md` に記録する。対応: `AC-006`、設計「受け入れ検証」。完了条件: 算出式と保存値が従来どおり一致し、AC-006を「検証済み」にできる。
- [x] 3.9 `README.md` の学習・閾値説明と `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/proposal.md` のAC-004を新しい算出元に合わせて更新する。対応: `REQ-007`・`REQ-035`、設計「移行とロールバック」、`AC-003`・`AC-004`。完了条件: 旧説明との矛盾がなく、対象グループの再学習・再検査手順が分かる。
- [x] 3.10 `npm run check`、`npx --no-install openspec validate fix-gpu-determinism-and-refit-threshold --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change fix-gpu-determinism-and-refit-threshold --phase implementation` を実行し、TCと品質結果を `evidence/automated.md` に記録する。対応: `REQ-038`・`REQ-007`・`REQ-035`、設計「試験設計」「網羅性確認」。完了条件: 自動試験、品質検査、参照テスト収集、厳密検証が成功する。
- [ ] 3.11 verify / archive 前にトレーサビリティ検査の `--phase complete` とOpenSpec厳密検証を実行し、全ACの証跡内容と対象環境をレビューする。実機確認だけ延期する場合は該当する3.3〜3.8を未完了のままREADMEの「延期中の受け入れ確認」へAC-IDとともに記録し、利用者の明示的了承を得て `--phase limited-archive` を実行する。対応: `AC-001`〜`AC-006`、設計「受け入れ検証」。完了条件: 選んだ工程の検査に合格し、未検証条件を完了と誤記しない。
