# 受け入れ検証記録

実行日: 2026-10-09。<br />
環境: macOS 26.6.2 (25G83) arm64、Python 3.13.15、pytest 9.1.1、OpenCV 5.0.0、Pydantic 2.13.4、Optuna 5.0.0。<br />
固定小規模画像とテストダブルによるローカル契約確認である。<br />
実モデルの学習・推論、Ubuntu 24.04 LTS、Windows 11、対象GPUの受け入れ確認はAC-007に残す。

| AC-ID | 状態 | 方法と結果 | 証跡・残る条件 |
| --- | --- | --- | --- |
| AC-001 | 検証済み | 有効・欠落・重複・不正IDをpytestで検証。256×256の固定画像で実CLI `check --model XX` が終了0となり、全範囲とグループ1の画像を目視した | [全範囲](check-all.png)、[グループ1](check-group-1.png)。対象OSの表示はAC-007で確認 |
| AC-002 | 検証済み | 実CLI `train-pre --model XX` と `train-pre --model XX --group 1` が終了0。元画像3件について全件時の各グループmanifestと、単独実行後の他グループ保持を確認。学習コマンドの全・単独選択と他グループ保持、学習時だけのデータ拡張と準備済み画像の不変はテストダブルを用いたpytestで確認 | `tests/test_preparation.py::test_group_req_002_s07`、`tests/test_training.py::test_group_req_022_s01`、`test_group_req_022_s02`、`test_group_req_006_s01`、`test_group_req_006_s02`。実モデルはAC-007 |
| AC-003 | 検証済み | 2グループの学習で後続グループに失敗を注入し、CLIの終了3、先行グループのcheckpoint保持と全件再実行の成功を確認。保存済み試行を保持して残りの試行から探索を再開することと、中断した学習成果物一式の復旧も確認 | `tests/test_training.py::test_group_req_008_s01`、`test_group_req_008_s03`、`tests/test_runtime.py::test_group_req_024_s03`。実モデル再開はAC-007 |
| AC-004 | 検証済み | 実CLI `test-pre --model XX` が終了0で全分割を保存。検査の全件・単独選択、分割対象、モデル不足時の推論前拒否と旧結果保持をpytestで確認 | `tests/test_preparation.py::test_group_req_025_s02`、`tests/test_evaluation.py::test_group_req_023_s01`、`test_group_req_023_s02`、`test_group_req_023_s03`。実モデルはAC-007 |
| AC-005 | 検証済み | 重複所属の分割を2グループで評価し、元画像ごとのJSON、グループ別画像、別々の判定、総合判定がないことを確認。未判定の集約も確認 | `tests/test_results.py::test_group_req_011_s03`、`test_group_req_011_s04`、`test_group_req_012_s05`、[異常結果画像](result-anomaly.png)。対象OS上の画像はAC-007 |
| AC-006 | 検証済み | 全件・単独再検査、後続グループ失敗と結果画像の書込み失敗、参照切替前後の中断注入、不正参照からの全件再生成、旧世代整理と次回再試行をpytestで確認。書込み失敗時は旧参照と旧JSONを保持し、推論失敗は分割単位で未判定として記録する | `tests/test_evaluation.py::test_group_req_013_s01`〜`test_group_req_013_s10`、`test_group_req_023_s05`、`tests/test_results.py::test_inference_failure_is_recorded_per_split`。対象OSの読戻しはAC-007 |
| AC-007 | 未検証 | 対象実機をこの環境で利用できない | Ubuntu 24.04 LTS・Windows 11でCPUと利用可能なGPUを使い、全件・単独の5 CLI、結果の読戻しと実デバイスを確認する。タスク6.7 |
| AC-008 | 未検証 | macOS上のfilelockと中断復旧はpytestで確認したが、対象OSの複数プロセス実行は未実施 | Ubuntu 24.04 LTS・Windows 11で同一型番・別型番の同時起動と中断後復旧を確認する。タスク6.8 |

## コマンドと品質結果

- `npm run check`: OpenSpec全件の厳格検証、format、lint、型検査、pytest 179件、リポジトリ検査、実装段階トレーサビリティが成功。
- `npx --no-install openspec validate group-scoped-inspection-models --strict`: 成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change group-scoped-inspection-models --phase implementation`: 成功。
- ローカルCLI: `check --model XX`、`train-pre --model XX`、`test-pre --model XX`、`train-pre --model XX --group 1` はいずれも終了0。

対象OS・実モデルの証跡がないため、AC-007とAC-008は未検証のままとする。<br />
この記録は運用開始の承認を意味しない。
