## 1. 設定契約と探索への適用

- [x] 1.1 `src/app/common/config.py` の `SamplerSettings` に既定値 5 の非負 `StrictInt` の `startup_trials` を追加し、小数・文字列・真偽値・負数を設定読込時に拒否する。対応: `REQ-030`、`REQ-031`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-001`、`TC-002`、`TC-004`、`TC-005`。完了条件: 有効値と省略時の値が読み取れ、不正値が探索前に拒否される。
- [x] 1.2 `src/app/model_training/search.py` の `create_study` で `sampler.startup_trials` を `TPESampler` の `n_startup_trials` に渡し、`MedianPruner` の引数を維持する。対応: `REQ-030`、設計「処理フロー」「技術判断」、`TC-001`〜`TC-003`。完了条件: 指定値が sampler に渡り、pruner と合計試行回数が従来どおりである。
- [x] 1.3 `config/part_XX.json` の sampler に `"startup_trials": 5` だけを追加し、`README.md` に型番・グループ別の設定方法、既定値、`execution.trials` 未満にしないと TPE 探索が行われないこと、全工程の再実行を記載する。対応: `REQ-030`、`AC-003`、設計「セキュリティ・性能・運用」「移行とロールバック」、`TC-002`、`TC-003`。完了条件: ひな形の他項目・値に差分がなく、説明と設定契約が一致する。

## 2. 自動試験

- [x] 2.1 `tests/test_training.py` に `TC-001`、`TC-002`、`TC-003` に対応する pytest テスト `test_req_030_s01_sampler_startup_trials`、`test_req_030_s02_default_startup_trials`、`test_req_030_s03_trials_within_startup` を追加して実行する。対応: `REQ-030` / `REQ-030-S01`〜`REQ-030-S03`、設計「試験設計」。完了条件: 0・正整数・省略・合計試行回数以上を実 Optuna で確認し、pruner 条件と実行試行数を検証する。
- [x] 2.2 `tests/test_config.py` に `TC-004`、`TC-005` に対応する pytest テスト `test_req_031_s01_negative_sampler_startup_trials` と `test_req_031_s02_noninteger_sampler_startup_trials` を追加して実行する。対応: `REQ-031` / `REQ-031-S01`・`REQ-031-S02`、設計「試験設計」「境界条件と失敗モード」。完了条件: 負数・小数・文字列・真偽値を拒否し、修正後の再読込が成功する。

## 3. 品質・運用受け入れ

- [x] 3.1 `npx --no-install openspec validate configure-tpe-startup-trials --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change configure-tpe-startup-trials --phase implementation`、`npm run check` を実行し、既存 `REQ-005-S01` と pruner warmup の回帰を確認する。対応: `AC-004`、設計「網羅性確認」「受け入れ検証」。完了条件: 各コマンドが成功し、結果を証跡に記録する。
- [ ] 3.2 対象 OS の実画像と変更後の型番設定で `check`、`train-pre`、`train`、`test-pre`、全件 `test` を順に実行し、指定値・省略時・不正値、ひな形・README、pruner 条件を確認する。`openspec/changes/archive/2026-10-23-configure-tpe-startup-trials/evidence/acceptance.md` に環境・版・日付・コマンド・結果・制約を記録し、design の受け入れ検証を更新する。対応: `AC-001`、`AC-002`、`AC-003`、`AC-004`、設計「受け入れ検証」「移行とロールバック」。完了条件: 各 AC の対象環境と結果を確認でき、状態「検証済み」、残る検証「なし」、実在証跡が揃う。対象 OS を利用できない場合は未完了・未検証のまま README の「延期中の受け入れ確認」に引き継ぐ。
- [x] 3.3 verify / archive 前に `npx --no-install openspec validate configure-tpe-startup-trials --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change configure-tpe-startup-trials --phase complete` を実行する。対象 OS の確認だけを延期する場合は `--phase limited-archive` を使用し、README の追跡記録を確認する。利用者の明示的了承は実際の制限付きアーカイブ前に別途得る。対応: `AC-001`、`AC-002`、`AC-003`、`AC-004`、設計「受け入れ検証」。完了条件: 制限付きアーカイブ工程の検査が成功し、証跡内容をレビューできる。
