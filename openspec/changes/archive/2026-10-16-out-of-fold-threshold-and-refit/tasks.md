## 1. 設定と保存契約

- [x] 1.1 `src/app/common/config.py` と `src/app/common/contracts.py` に従来・新方式、分割数または1枚ずつ、百分位、マージン、交差検証・最終学習の記録型と検証を追加する。`config/part_XX.json` に新方式の設定例を示す。対応: `REQ-033`、`REQ-034`、設計「データ契約と状態」、`TC-003`、`TC-004`。完了条件: 既存設定を読め、不正条件・不正スコアを拒否できる。

## 2. 学習フロー

- [x] 2.1 `src/app/model_training/search.py` にブラックリスト除外後の元画像を使う再現可能な交差検証分割を追加する。対応: `REQ-033`、設計「処理フロー」「交差検証と探索の分離」、`TC-001`〜`TC-003`。完了条件: 全元画像が一度だけ検証側となり、各分割の学習側と交差しない。
- [x] 2.2 `src/app/model_training/trainer.py` と `cli.py` で最良条件の分割別学習・検証推論を実行し、元画像・分割画像に対応するスコアを収集する。対応: `REQ-033`、設計「責務一覧」「処理フロー」、`TC-001`、`TC-002`。完了条件: 固定分割の探索値を維持し、交差検証の全スコアを対応付けられる。
- [x] 2.3 `src/app/model_training/cli.py` と `artifacts.py` で新方式の百分位・マージン閾値を算出し、空・非有限・件数不一致を理由付きで拒否する。対応: `REQ-034`、設計「データ契約と状態」「境界条件と失敗モード」、`TC-004`、`TC-005`。完了条件: 数値境界と失敗時の旧一式保持を確認できる。
- [x] 2.4 `src/app/model_training/trainer.py` と `cli.py` で最良条件による全対象正常画像の最終学習を両閾値方式に追加し、独立したcheckpointを成果物公開へ渡す。対応: `REQ-035`、設計「処理フロー」「最終学習と成果物公開」、`TC-006`〜`TC-008`。完了条件: ブラックリスト除外後の全画像だけを学習し、失敗時に旧一式が残る。

## 3. 成果物と自動試験

- [x] 3.1 `src/app/model_training/artifacts.py` と共有契約に方式、交差検証分割、元画像・分割画像別スコア、全件学習元画像を保存し、既存の3成果物トランザクションを適用する。対応: `REQ-034`、`REQ-035`、`REQ-007`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-004`、`TC-006`、`TC-009`、`TC-011`。完了条件: checkpoint・設定・結果の閾値が一致し、中断後に旧一式へ復旧できる。
- [x] 3.2 `src/app/model_evaluation/evaluation.py` の読戻し契約と `src/app/model_training/search.py` の再開条件を新しい方式・分割設定に整合させる。対応: `REQ-007`、設計「インターフェースと失敗時の結果」「移行とロールバック」、`TC-012`。完了条件: 不整合を推論前に拒否し、異条件の探索履歴を混ぜない。
- [x] 3.3 `tests/test_training.py` に `TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005` の指定pytestを実装し、元画像の非重複・全件被覆、1枚ずつ、設定不備、算出値と証跡、評価失敗を検証する。対応: `REQ-033`、`REQ-034`、設計「試験設計」。完了条件: 設計表の5関数と `uv run --locked pytest tests/test_training.py -q` が成功する。
- [x] 3.4 `tests/test_training.py` に `TC-006`、`TC-007`、`TC-008`、`TC-009`、`TC-010`、`TC-011`、`TC-012`、`TC-013` の指定pytestを実装し、全件最終学習、従来閾値、保存失敗、3成果物整合、キャッシュ、復旧、不整合拒否、グループ独立性を検証する。対応: `REQ-035`、`REQ-007`、設計「試験設計」。完了条件: 設計表の8関数と `uv run --locked pytest tests/test_training.py -q` が成功する。
- [x] 3.5 `README.md` の用語集と学習手順、`config/part_XX.json` の設定例を新旧方式・追加学習回数・再学習と検査結果再生成に合わせて更新する。対応: `REQ-033`、`REQ-034`、`REQ-035`、設計「移行とロールバック」。完了条件: 設定値と保存結果、運用手順を照合できる。

## 4. 品質と受け入れ

- [x] 4.1 `uv run --locked pytest`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change out-of-fold-threshold-and-refit --phase implementation` を実行し、設計の全TC-IDと結果を証跡へ記録する。対応: `REQ-033`、`REQ-034`、`REQ-035`、`REQ-007`、`AC-001`〜`AC-005`、設計「試験設計」「受け入れ検証」。完了条件: 自動試験・品質検査・参照テスト収集が成功する。
- [ ] 4.2 Ubuntu 24.04 LTS・Windows 11 の対象実機で、指定分割数・1枚ずつ・従来方式の `train` と `test`、実スコアと閾値の再計算、全件学習checkpointの読戻し、3成果物整合、入力不備・失敗と復旧を確認し、環境・版・デバイス・コマンド・結果を `openspec/changes/archive/2026-10-16-out-of-fold-threshold-and-refit/evidence/acceptance.md` に記録して design の受け入れ検証を更新する。対応: `AC-001`〜`AC-006`、設計「受け入れ検証」。完了条件: 全AC-IDが対象環境の証跡で検証済みとなる。
- [x] 4.3 verify / archive 前に `npx --no-install openspec validate out-of-fold-threshold-and-refit --strict` と、通常は `uv run --locked python scripts/check_openspec_traceability.py --change out-of-fold-threshold-and-refit --phase complete` を実行する。実機確認だけを延期する場合は `README.md` の延期表にAC-ID・未完了タスク4.2・確認内容を記載し、`--phase limited-archive` で検査して利用者の明示的了承を得る。対応: `AC-001`〜`AC-006`、設計「受け入れ検証」。完了条件: 対応する工程の両検査が成功し、延期時は未検証状態と残るリスクが記録される。
