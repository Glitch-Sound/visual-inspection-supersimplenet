## 1. 設定・保存契約

- [x] 1.1 `REQ-037` `REQ-018` `REQ-038`: `src/app/common/config.py` と `src/app/common/contracts.py` に閾値単位、最少件数、分割別算出値・由来・件数、分割別手動上書き、結果フィールドの型と厳格な検証を追加する。<br />
対応: `REQ-037`、`REQ-018`、`REQ-038`、設計「データ契約と状態」、`TC-004`、`TC-005`、`TC-013`。<br />
完了条件: 既存設定はグループ単位で読め、不正単位・件数・ID・数値は理由付きで拒否される。

## 2. 学習と成果物

- [x] 2.1 `REQ-036`: `src/app/model_training/artifacts.py` で検証側スコアを分割IDに対応付け、件数を満たすIDの閾値を既存のパーセンタイル・マージン・上限で算出する。<br />
対応: `REQ-036`、設計「処理フロー」、`TC-001`。<br />
完了条件: 分割IDごとのスコアだけで算出され、グループ値は従来の全スコアから算出される。
- [x] 2.2 `REQ-036`: `src/app/model_training/artifacts.py` と共通保存契約で件数不足の代替値・警告を生成し、設定・最良試行・checkpointを一式保存する。<br />
対応: `REQ-036`、設計「データ契約と状態」「技術判断」、`TC-002`、`TC-003`。<br />
完了条件: 0件と境界未満でグループ値・理由・件数が保存され、既定のグループ単位は従来値と一致する。
- [x] 2.3 `REQ-037`: `src/app/model_training/search.py` の再開契約と `src/app/model_evaluation/evaluation.py` の学習成果物照合に単位・件数・分割別値・由来・ID集合を加える。<br />
対応: `REQ-037`、設計「処理フロー」「インターフェースと失敗時の結果」、`TC-006`。<br />
完了条件: 設定変更は `train --restart` を案内し、不一致は推論前に拒否して旧結果を保持する。

## 3. 検査と結果

- [x] 3.1 `REQ-018`: `src/app/model_evaluation/evaluation.py` でグループ単位の既存選択を維持し、分割ID単位では手動上書き、分割別算出値、グループ代替値の順に選択する。<br />
対応: `REQ-018`、設計「処理フロー」「技術判断」、`TC-009`〜`TC-014`。<br />
完了条件: 0・1および同値スコアを含む判定と、手動上書き後の暫定値不変を確認できる。
- [x] 3.2 `REQ-038` `REQ-018`: `src/app/model_evaluation/evaluation.py` と `src/app/common/contracts.py` で分割結果に使用値・由来を記録し、推論エラー時も残す。<br />
対応: `REQ-038`、`REQ-018`、設計「データ契約と状態」、`TC-007`、`TC-008`。<br />
完了条件: JSON読戻しで全分割の値・由来、異常優先集約、エラー時の未判定を確認できる。

## 4. 自動試験と案内

- [x] 4.1 `pytest` `tests/test_training.py` に `TC-001`、`TC-002`、`TC-003` の3試験を実装し、分割別算出、件数不足、既定互換を検証する。<br />
対応: `REQ-036`、設計「試験設計」。<br />
完了条件: 設計に記載した3つのpytest関数が成功する。
- [x] 4.2 `pytest` `tests/test_config.py` に `TC-004`、`TC-005`、`tests/test_evaluation.py` に `TC-006`、`TC-013` の試験を実装する。<br />
対応: `REQ-037`、`REQ-018`、設計「試験設計」。<br />
完了条件: 不正設定と成果物不一致が理由付きで拒否され、旧成果物・結果が保持される。
- [x] 4.3 `pytest` `tests/test_evaluation.py` に `TC-007`、`TC-008`、`TC-009`、`TC-010`、`TC-011`、`TC-012`、`TC-014`、`TC-015` の試験を実装し、結果由来、推論失敗、従来互換、境界、手動上書きと成果物不整合を検証する。<br />
対応: `REQ-038`、`REQ-018`、設計「試験設計」。<br />
完了条件: 設計に記載した8つのpytest関数が成功する。
- [x] 4.4 `config/part_XX.json` と `README.md` の設定・用語・再学習手順を更新する。<br />
対応: `REQ-036`、`REQ-018`、設計「移行とロールバック」。<br />
完了条件: グループ単位の既定値、分割ID別の設定例、件数不足の警告、`train --restart` と結果再生成を確認できる。

## 5. 品質・受け入れ

- [x] 5.1 `uv run --locked pytest`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change per-split-threshold --phase implementation` を実行し、`AC-001`〜`AC-005` の自動検証結果を `openspec/changes/per-split-threshold/evidence/acceptance.md` に環境・版・日付・コマンドとともに記録する。<br />
対応: 設計「試験設計」「受け入れ検証」。<br />
完了条件: 全試験・品質検査・収集検査が成功し、自動試験の検証範囲を証跡で確認できる。
- [ ] 5.2 Ubuntu 24.04 LTSとWindows 11の実画像・利用可能なCPU/GPUで、`AC-001`〜`AC-004` と `AC-006` のグループ互換、分割別算出・代替、上書き、JSON読戻しを確認し、`openspec/changes/per-split-threshold/evidence/acceptance.md` に条件・結果・制約を記録する。<br />
対応: 設計「受け入れ検証」。<br />
完了条件: 対象OSの結果をレビューし、対応する受け入れ条件の状態と残る検証を更新できる。
- [ ] 5.3 `AC-005` の不正設定・成果物不一致・旧結果保持を対象環境で確認し、同じ証跡に結果を記録する。<br />
対応: 設計「受け入れ検証」。<br />
完了条件: 拒否理由と旧成果物・結果の読戻しを確認できる。
- [x] 5.4 verify / archive 前に `npx --no-install openspec validate per-split-threshold --strict` と、通常は `uv run --locked python scripts/check_openspec_traceability.py --change per-split-threshold --phase complete` を実行する。<br />
対象OSの受け入れ確認だけを延期する場合は、残るAC-IDと未完了タスクを `README.md` の「延期中の受け入れ確認」に記録し、利用者の明示的な了承を得てから `--phase limited-archive` を実行する。<br />
対応: 設計「網羅性確認」「受け入れ検証」。<br />
完了条件: 該当工程の厳密検証とトレーサビリティ検査が成功し、証跡と受け入れ状態が一致する。
