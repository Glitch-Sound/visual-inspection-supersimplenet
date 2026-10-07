## 1. バックボーンと再学習契約

- [x] 1.1 `src/app/common/model_adapter.py`の固定バックボーンを`wide_resnet50_2.racm_in1k`へ変更し、学習と検査の共有入口へ適用する。対応: `REQ-020`、設計「技術判断」、`TC-001`。完了条件: モデル生成時に新しい重み名が渡る。
- [x] 1.2 `src/app/model_training/artifacts.py`の既存`train --restart`削除契約を確認し、旧探索履歴とcheckpointが残らないことを自動試験で維持する。対応: `REQ-020`、設計「移行とロールバック」、`TC-002`。完了条件: 旧成果物が対象型番だけ削除される。

## 2. 検査進捗の実装

- [x] 2.1 `src/app/model_evaluation/evaluation.py`に元画像単位の進捗通知を追加し、manifest読込後の初期値と判定集約後の件数を報告する。対応: `NREQ-003`、設計「処理フロー」、`TC-004`, `TC-005`, `TC-006`。完了条件: 個別エラー・未判定でも一件進み、全体失敗では未処理分を進めない。
- [x] 2.2 `src/app/model_evaluation/cli.py`に端末用バーと非端末用件数表示を接続し、標準出力JSONを変えない。対応: `NREQ-003`、設計「インターフェースと失敗時の結果」、`TC-003`, `TC-004`。完了条件: 標準エラーに進捗が出て、標準出力は従来どおり一件のJSONである。

## 3. 自動試験・文書・品質確認

- [x] 3.1 `tests/test_training.py`に新重み指定とtimm特徴抽出器構築のpytestテストを追加し、再学習のpytestテストを実行する。対応: `REQ-020` / `REQ-020-S01` / `REQ-020-S02`、`TC-001`、`TC-002`、設計「試験設計」。完了条件: `tests/test_training.py::test_model_adapter_uses_racm_backbone`と`tests/test_training.py::test_training_restart_replaces_only_derived_artifacts`が成功する。
- [x] 3.2 `tests/test_runtime.py`と`tests/test_evaluation.py`に端末・非端末・未判定・個別エラー・全体失敗のpytestテストを追加して実行する。対応: `NREQ-003` / `NREQ-003-S01` / `NREQ-003-S02` / `NREQ-003-S03` / `NREQ-003-S04`、`TC-003`、`TC-004`、`TC-005`、`TC-006`、設計「試験設計」。完了条件: 指定した4 pytest関数が成功し、標準出力と終了コードの契約を確認できる。
- [x] 3.3 `README.md`に新バックボーン、全型番の`train --restart`、閾値・表示範囲の見直し、`test --restart`、検査進捗の読み方を記載する。対応: `REQ-020`、`NREQ-003`、`AC-004`、設計「移行とロールバック」。完了条件: 旧成果物を再利用しない順序と元画像単位の進捗が読める。
- [x] 3.4 対応自動試験、`npm run check`、`npx --no-install openspec validate show-test-progress-and-update-backbone --strict`、トレーサビリティ検査`--phase implementation`を実行する。対応: `REQ-020`、`NREQ-003`、設計「試験設計」。完了条件: 自動試験と品質検査が成功し、参照テストの収集が可能である。

## 4. 対象環境での受け入れ確認

- [ ] 4.1 Ubuntu 24.04 LTSとWindows 11の端末・非端末で`test`の元画像進捗、標準出力JSONと終了コードを確認し、証跡を記録する。対応: `NREQ-003`、`AC-001`、設計「受け入れ検証」。完了条件: 両OSの結果、環境・版、実行手順を証跡で確認し、AC-001を検証済みにできる。
- [ ] 4.2 Ubuntu 24.04 LTSとWindows 11の実画像で未判定・個別分割エラー・全体失敗時の進捗と終了状態を確認し、証跡を記録する。対応: `NREQ-003`、`AC-002`、設計「受け入れ検証」。完了条件: 両OSの例外時の件数と終了状態を証跡で確認し、AC-002を検証済みにできる。
- [ ] 4.3 対象型番で`racm_in1k`の実重み取得、`train --restart`、checkpoint検査を確認し、証跡を記録する。対応: `REQ-020`、`AC-003`、設計「受け入れ検証」。完了条件: 実重みによる学習と検査を証跡で確認し、AC-003を検証済みにできる。
- [ ] 4.4 全型番で旧探索履歴・checkpointの破棄、暫定閾値・表示範囲の見直し、`test --restart`による旧結果再生成を確認し、証跡を記録する。対応: `REQ-020`、`AC-004`、設計「受け入れ検証」。完了条件: 全型番の移行結果を証跡で確認し、AC-004を検証済みにできる.
