## 1. 結果パスと共通ディレクトリ操作

- [x] 1.1 `src/app/image_preparation/preparation.py` の段階作成・ディレクトリ置換処理を `src/app/common/atomic.py` に移し、準備側の呼出しを切り替える。結果専用の退避・復旧は共通処理へ混ぜない。対応: `REQ-013`、設計「業務フローと責務」「技術判断」、`TC-001`、`TC-003`、`TC-004`。完了条件: 準備の既存テストが成功し、置換前失敗で旧準備成果物を保持する。
- [x] 1.2 `src/app/common/paths.py` の `result_generations` と `result_current` を削除し、安全確認付きのグループ別結果パスを追加する。対応: `REQ-028`、設計「データ契約と状態」、`TC-021`、`TC-022`。完了条件: ID 0、9、10、100 の固定名を返し、親または対象のリンクを拒否する。

## 2. 結果公開と検査CLI

- [x] 2.1 `src/app/common/result_index.py` から `read_current`、`create_generation`、`publish_current`、`cleanup_generations` を削除し、全対象用ステージ、正規グループの退避付き置換、次回開始時の復旧、設定外グループの全件時整理を実装する。`src/app/common/cli.py` の旧世代整理呼出しを外す。対応: `REQ-013`、設計「処理フロー」「技術判断」「境界条件と失敗モード」、`TC-001`～`TC-011`。完了条件: 旧結果の欠落時は退避から復旧でき、リンク・管理外エントリを削除せず、旧 `current.json` と `generations/` を変更しない。
- [x] 2.2 `src/app/model_evaluation/cli.py` の `test` を全対象グループの一時結果完成後に公開する順序へ変更し、単独検査は指定グループのみを置換する。最終公開後にだけ進捗を完了させ、終了表示を結果ルートに変える。対応: `REQ-013`、`REQ-023`、`REQ-028`、`NREQ-003`、設計「処理フロー」「インターフェースと失敗時の結果」、`TC-001`～`TC-022`。完了条件: 作成中の後続グループ失敗では全旧結果を保持し、完了後の保存先と表示が新契約に一致する。

## 3. 自動試験・文書・受け入れ

- [x] 3.1 `tests/test_group_artifact_names.py` と `tests/test_evaluation.py` の `TC-021`、`TC-022` を新しい固定結果パスで作成・更新する。`current.json` と `generations/` を前提にしたテストを削除または新契約へ置換する。対応: `REQ-028` / `REQ-028-S01`・`REQ-028-S02`、設計「試験設計」、`TC-021`、`TC-022`。完了条件: 両ケースのpytestが成功し、境界ID、整数ID、直下のファイル種別、旧ファイル除去と終了表示を検証する。
- [x] 3.2 `tests/test_evaluation.py` と `tests/test_training.py` の結果参照を固定パスへ更新し、全件・単独、作成中失敗、設定外整理、欠落モデル、旧結果保持のpytestを実装する。対応: `REQ-013`、`REQ-023`、設計「試験設計」、`TC-001`、`TC-002`、`TC-003`、`TC-006`、`TC-008`、`TC-010`、`TC-011`、`TC-016`、`TC-017`、`TC-018`、`TC-019`、`TC-020`。完了条件: 列挙した全ケースのpytestが成功する。
- [x] 3.3 `tests/test_evaluation.py` に退避直後・新結果公開直後の停止点、復旧不能、親・対象リンク、管理外ファイル、準備CLIの非干渉を確認するpytestを実装する。対応: `REQ-013`、設計「技術判断」「境界条件と失敗モード」「試験設計」、`TC-004`、`TC-005`、`TC-007`、`TC-009`。完了条件: 列挙した全ケースのpytestが成功し、各故障点から旧または新の完全な状態へ復旧でき、管理外の内容が不変である。
- [x] 3.4 `tests/test_evaluation.py` の進捗試験を新公開時点に合わせ、端末・非端末、未判定、公開失敗のpytestを実装する。対応: `NREQ-003`、設計「処理フロー」「試験設計」、`TC-012`、`TC-013`、`TC-014`、`TC-015`。完了条件: 列挙した全ケースのpytestが成功し、進捗と標準出力JSONの契約を確認できる。
- [x] 3.5 `README.md` の用語集、成果物表、結果読戻し、再実行手順と `scripts/run_visual_inspection_smoke.py` の読戻し先を固定グループパスへ更新し、旧形式の移行・自動削除をしないことと検査停止・復旧後の読戻しを案内する。対応: `REQ-013`、`REQ-028`、`AC-001`、`AC-005`、設計「移行とロールバック」。完了条件: README・スモーク試験とspec・CLIのパス、表示、運用手順が一致する。
- [ ] 3.6 Ubuntu 24.04 LTSとWindows 11で `AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005` を確認する。固定保存先の読戻し、全件・単独、公開前失敗と公開中断後の復旧、リンク拒否、旧形式不変、準備・学習・検査の全再実行を実施し、コマンド・日付・環境・版・結果を `openspec/changes/archive/2026-10-24-simplify-result-layout/evidence/acceptance.md` に記録してdesignの「受け入れ検証」を更新する。対応: `AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005`、設計「受け入れ検証」、全TC-ID。完了条件: 対象環境で各条件を確認し、実在証跡・状態「検証済み」・残る検証「なし」が揃う。実機を利用できずこの確認だけを延期する場合は未完了のままREADMEの「延期中の受け入れ確認」にAC-ID・本タスク番号・確認内容を記録する。
- [x] 3.7 `uv run --locked pytest`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change simplify-result-layout --phase implementation` を実行し、全TC-IDの収集・成功と品質ゲートを確認する。verify / archive前は `npx --no-install openspec validate simplify-result-layout --strict` と通常 `--phase complete`、実機確認だけを延期する場合は `--phase limited-archive` の対応検査を実行する。対応: 全要件、全AC-ID、設計「試験設計」「受け入れ検証」、`TC-001`～`TC-022`。完了条件: 自動試験・品質確認の結果を証跡に残し、実機確認の状態と区別して判定する。
