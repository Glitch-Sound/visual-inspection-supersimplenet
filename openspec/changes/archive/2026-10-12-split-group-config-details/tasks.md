## 1. 設定契約

- [x] 1.1 `src/app/common/config.py` で `groups` と `group_detail` のID対応、キー書式、項目の配置を検証し、内部 `GroupConfig` を組み立てる。対応: `REQ-021`、設計「データ契約と状態」、`TC-001`〜`TC-005`。完了条件: 新形式を読み、欠落・余分・混在を拒否する。
- [x] 1.2 `config/part_XX.json` と `tests/fixtures/model_config.json` を新形式へ移し、READMEの設定表と移行手順を更新する。対応: `REQ-021`、設計「移行とロールバック」、`TC-001`〜`TC-005`。完了条件: 雛形とfixtureが新形式として読める。
- [x] 1.3 `src/app/common/config.py` の暫定閾値書戻しを対象IDの `group_detail` へ変更する。対応: `REQ-029`、設計「処理フロー」、`TC-006`、`TC-007`。完了条件: 対象だけ更新し、不正設定では書き込まない。

## 2. 試験

- [x] 2.1 `tests/test_config.py` と設定を操作する既存fixture・試験を更新し、`TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`、`TC-006`、`TC-007` の pytest テストを作成・実行する。対応: `REQ-021`、`REQ-029`、設計「試験設計」。完了条件: 全Scenarioのテストと既存の設定・学習・検査テストが成功する。

## 3. 品質・受け入れ

- [x] 3.1 `npm run check` と `uv run --locked python scripts/check_openspec_traceability.py --change split-group-config-details --phase implementation` を実行し結果を記録する。対応: `REQ-021`、`REQ-029`、設計「試験設計」。完了条件: 品質検査と参照テスト収集が成功する。
- [ ] 3.3 `AC-001` を Ubuntu 24.04 LTS・Windows 11の新形式・複数グループで5 CLIを全件・単独実行し、`openspec/changes/split-group-config-details/evidence/acceptance.md` に記録する。対応: `AC-001`、設計「受け入れ検証」。完了条件: 対象OSの結果と読戻しを確認する。実機がなければ未完了のままREADMEへ延期を記録する。
- [ ] 3.4 `AC-002` を両対象OSで欠落・余分・非標準キーと旧形式混在の設定を使い、入力不備と既存成果物の不変を確認して同じ証跡に記録する。対応: `AC-002`、設計「受け入れ検証」。完了条件: 各拒否と不変を確認する。実機がなければ未完了のままREADMEへ延期を記録する。
- [ ] 3.5 `AC-003` を両対象OSで実モデルの単独グループ学習により確認し、対象だけの閾値書戻しを同じ証跡に記録する。対応: `AC-003`、設計「受け入れ検証」。完了条件: 対象・他グループの設定とcheckpointを照合する。実機がなければ未完了のままREADMEへ延期を記録する。
- [x] 3.6 verify / archive 前に `npx --no-install openspec validate split-group-config-details --strict` と、通常は `--phase complete`、実機確認だけ延期する場合は `--phase limited-archive` のトレーサビリティ検査を実行する。対応: `AC-001`〜`AC-003`、設計「受け入れ検証」。完了条件: 適用する工程の検査が成功する。
