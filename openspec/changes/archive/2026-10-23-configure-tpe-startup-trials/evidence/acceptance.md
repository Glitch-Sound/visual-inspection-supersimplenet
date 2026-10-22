# 受け入れ確認の証跡

## 自動試験と品質確認

- 実施日: 2026-10-23。
- 環境: macOS 27.0.1 (Darwin)、Python 3.13.15、ロック済み依存関係。
- `uv run --locked pytest -q tests/test_training.py::test_req_030_s01_sampler_startup_trials tests/test_training.py::test_req_030_s02_default_startup_trials tests/test_training.py::test_req_030_s03_trials_within_startup tests/test_config.py::test_req_031_s01_negative_sampler_startup_trials tests/test_config.py::test_req_031_s02_noninteger_sampler_startup_trials`: 9 件成功。
- `npx --no-install openspec validate configure-tpe-startup-trials --strict`: 成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change configure-tpe-startup-trials --phase implementation`: 成功。<br />
  参照 pytest の収集可否を確認した。
- `npm run check`: 成功。<br />
  OpenSpec 全件の厳密検証、Ruff format・lint、Pyright、pytest 277 件、リポジトリ検査、進行中 change の実装段階トレーサビリティ検査が通過した。
- `uv run --locked python scripts/check_openspec_traceability.py --change configure-tpe-startup-trials --phase limited-archive`: 成功。<br />
  AC-001、AC-002、AC-004 とタスク 3.2 は未検証・未完了のまま追跡する。
- `git diff -- openspec/specs/visual-inspection/model-training/spec.md config/part_XX.json`: 正式仕様の `REQ-005-S01` に差分はなく、設定ひな形の差分は sampler の `startup_trials: 5` の追加だけだった。
- `git diff --check`: 成功。

## AC ごとの確認状態

| ID | 自動試験・文書で確認した結果 | 対象 OS・実画像で残る確認 | 状態 |
| --- | --- | --- | --- |
| AC-001 | 0、正整数、省略時 5、合計試行回数以上の実 Optuna 試行を確認 | Ubuntu 24.04 LTS と Windows 11 の実画像探索 | 未検証 |
| AC-002 | 負数、小数、文字列、真偽値の入力拒否と修正後の読込を確認 | 両 OS の CLI 表示と学習前の終了 | 未検証 |
| AC-003 | `config/part_XX.json` の値 5、他項目の不変、README の設定方法・合計試行回数との関係・再実行手順を確認 | なし | 検証済み |
| AC-004 | MedianPruner の引数 5・40・10 を確認し、全自動試験が成功 | 両 OS の実画像で準備・学習・検査を通す | 未検証 |

対象 OS はこの環境では利用できず、実画像もリポジトリ内にない。<br />
自動試験の成功を実機確認の完了とは扱わない。
