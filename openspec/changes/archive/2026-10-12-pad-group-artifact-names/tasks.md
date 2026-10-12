## 1. 保存名と参照契約

- [x] 1.1 `src/app/common/paths.py` に最低2桁のグループ保存名を定義し、確認画像、学習準備、探索、checkpointの保存先へ適用する。対応: `REQ-026`、`REQ-027`、`REQ-028`、設計「データ契約と状態」「技術判断」、`TC-001`、`TC-002`、`TC-004`。完了条件: ID 0、9、10、100が指定の名前になる。
- [x] 1.2 `src/app/common/result_index.py` の現行参照検証を新名へ合わせ、旧名を拒否する。対応: `REQ-027`、`REQ-028`、設計「インターフェースと失敗時の結果」、`TC-003`、`TC-005`。完了条件: 新名を読戻せ、旧名を不正参照として拒否する。

## 2. 各能力の保存処理

- [x] 2.1 `src/app/image_preparation/preparation.py`、`src/app/model_evaluation/cli.py` に共通名を適用し、READMEの保存先と再生成手順を更新する。対応: `REQ-026`、`REQ-027`、`REQ-028`、設計「業務フローと責務」「移行とロールバック」、`TC-001`〜`TC-005`。完了条件: 保存先と参照先が一致し、ID値は整数のままである。

## 3. 試験と受け入れ

- [x] 3.1 `tests/test_group_artifact_names.py` に `TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005` の pytest テストを追加・実行し、既存の保存先期待値を更新する。対応: `REQ-026`〜`REQ-028`、設計「試験設計」。完了条件: 5シナリオと関連する既存試験が成功する。
- [x] 3.2 `npm run check` と `uv run --locked python scripts/check_openspec_traceability.py --change pad-group-artifact-names --phase implementation` を実行して記録する。対応: `REQ-026`〜`REQ-028`、設計「試験設計」。完了条件: 品質検査と参照テスト収集が成功する。
- [ ] 3.3 `AC-001` を Ubuntu 24.04 LTS と Windows 11 の対象環境で全CLI再生成によって検証し、`openspec/changes/pad-group-artifact-names/evidence/acceptance.md` に記録する。対応: `AC-001`、設計「受け入れ検証」。完了条件: ID 0・10の保存名と整数IDを対象環境で確認し、状態「検証済み」、残る検証「なし」とする。実機が利用できなければ未完了のままREADMEへ延期を記録する。
- [ ] 3.4 `AC-002` を両対象OSで旧成果物退避後の準備・学習・全件検査と現行参照読戻しによって検証し、同じ証跡に記録する。対応: `AC-002`、設計「受け入れ検証」。完了条件: 再生成結果を対象環境で読み戻し、状態「検証済み」、残る検証「なし」とする。実機が利用できなければ未完了のままREADMEへ延期を記録する。
- [x] 3.5 verify / archive 前に `npx --no-install openspec validate pad-group-artifact-names --strict` と、通常は `--phase complete`、対象実機の確認だけ延期する場合は `--phase limited-archive` のトレーサビリティ検査を実行する。対応: `AC-001`、`AC-002`、設計「受け入れ検証」。完了条件: 適用する工程の検査が成功する。
