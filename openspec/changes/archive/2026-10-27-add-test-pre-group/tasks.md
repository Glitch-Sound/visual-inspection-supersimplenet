## 1. 契約と処理

- [x] 1.1 `src/app/common/paths.py` と `src/app/image_preparation/cli.py` にグループ別試験準備パスと `test-pre --group` を追加し、対象IDを検証して実行記録に示す。対応: `REQ-003`、設計「処理フロー」「インターフェースと失敗時の結果」、`TC-001`〜`TC-007`。完了条件: 単独・全件の対象と未知ID拒否がCLIで一致する。
- [x] 1.2 `src/app/common/config.py` と `src/app/image_preparation/preparation.py` で試験指紋、グループ別manifest、対象分割を生成し、全件の位置合わせ再利用と段階公開を行う。対応: `REQ-025`、設計「データ契約と状態」、`TC-008`〜`TC-011`。完了条件: manifestのIDと指紋が対象設定と一致する。
- [x] 1.3 `src/app/model_evaluation/cli.py` と `evaluation.py` で対象グループの試験準備を検査前に照合して使用し、欠落・不整合をグループID付きで拒否する。対応: `REQ-041`、設計「処理フロー」「インターフェースと失敗時の結果」、`TC-012`〜`TC-014`。完了条件: 単独・全件が対応する準備を使用し旧結果を保全する。

## 2. 自動試験

- [x] 2.1 `tests/test_test_pre_group.py` に単独・全件、未判定、範囲外、読込み失敗、一時領域、未知IDの `TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`、`TC-006`、`TC-007` を実装・実行する。対応: `REQ-003`、設計「試験設計」。完了条件: 7つのpytest関数が成功する。
- [x] 2.2 `tests/test_test_pre_group.py` に学習・試験manifest、指紋変更と不変の `TC-008`、`TC-009`、`TC-010`、`TC-011` を実装・実行する。対応: `REQ-025`、設計「試験設計」。完了条件: 4つのpytest関数が成功する。
- [x] 2.3 `tests/test_test_pre_group.py` に単独・全件検査と欠落・不整合の `TC-012`、`TC-013`、`TC-014` を実装・実行する。対応: `REQ-041`、設計「試験設計」。完了条件: 3つのpytest関数が成功する。
- [x] 2.4 既存の準備・検査・設定・スモーク試験を新保存先に更新し、`scripts/run_visual_inspection_smoke.py` が単独 `test-pre --group` とグループ別manifestを検証するよう変更する。対応: `REQ-003`、`REQ-041`、設計「データ契約と状態」「試験設計」、`TC-001`、`TC-012`。完了条件: 関連テストとスモーク契約が成功する。

## 3. 案内と受け入れ

- [x] 3.1 `README.md` に単独 `test-pre`、グループ別保存先、全工程再実行を記載し、`npm run check` と `--phase implementation` のトレーサビリティ検査を成功させる。対応: `REQ-003`、`REQ-025`、`REQ-041`、設計「移行とロールバック」「試験設計」、`TC-001`〜`TC-014`。完了条件: 文書とCLIが一致し品質検査が成功する。
- [ ] 3.2 Ubuntu 24.04 LTSとApple silicon macOSの対象環境で実画像を用い、全件・単独の準備・学習・検査、例外と読戻しを確認し、`evidence/acceptance.md` と設計の受け入れ検証を更新する。対応: `AC-001`、`AC-002`、`AC-003`、`AC-004`、設計「受け入れ検証」。完了条件: 全ACの対象環境・結果が記録され、残る検証がない。
- [x] 3.3 verify / archive 前に `npx --no-install openspec validate add-test-pre-group --strict` と `--phase complete` のトレーサビリティ検査を実行する。対象環境だけ延期する場合は README の追跡記録を作り、明示的了承後に `--phase limited-archive` で検査する。対応: `AC-001`〜`AC-004`、設計「受け入れ検証」。完了条件: 適用工程の検査が成功する。
