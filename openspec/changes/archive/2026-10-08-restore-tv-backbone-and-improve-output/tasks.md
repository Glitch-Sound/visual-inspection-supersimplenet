## 1. バックボーンと移行

- [x] 1.1 `src/app/common/model_adapter.py`の固定バックボーンを`wide_resnet50_2.tv_in1k`へ戻す。対応: `REQ-020`、設計「技術判断」、`TC-001`。完了条件: 学習と検査の共有入口が新しい指定を使用する。
- [x] 1.2 `tests/test_training.py`で`TC-001`と`TC-002`のpytestテストを更新・実行し、実ライブラリ構築・重み指定と旧成果物削除を検証する。対応: `REQ-020-S01` / `REQ-020-S02`、設計「試験設計」。完了条件: `test_model_adapter_uses_tv_backbone`と`test_training_restart_replaces_only_derived_artifacts`が成功する。

## 2. 異常結果画像

- [x] 2.1 `src/app/model_evaluation/evaluation.py`で異常分割だけ元画像を左、従来の重ね合わせ画像を右に横結合し、同じ結果パスへ保存する。対応: `REQ-010`、設計「技術判断」、`TC-003`〜`TC-006`。完了条件: 異常時の横幅が入力の2倍で、正常時の画素とサイズは不変。
- [x] 2.2 `tests/test_evaluation.py`の`TC-003`、`TC-004`、`TC-005`、`TC-006`のpytestテストを更新・実行し、正常画像、異常画像の左右画素、色尺度、スコアと判定、前処理の不変を確認する。対応: `REQ-010-S01`〜`REQ-010-S04`、設計「試験設計」。完了条件: 関連pytestが成功する。

## 3. 学習条件の表示

- [x] 3.1 `src/app/model_training/search.py`に選択済み条件の開始通知と試行終了通知を追加し、既存履歴を再通知しない。対応: `NREQ-004`、設計「技術判断」、`TC-007`〜`TC-009`。完了条件: 完了・枝刈り・失敗・再開で通知値が一致する。
- [x] 3.2 `src/app/model_training/cli.py`で探索概要、各試行の2列条件表、終了状態と完了指標、最良試行条件を標準エラーへ表示する。`tests/test_training.py`と`tests/test_runtime.py`で`TC-007`、`TC-008`、`TC-009`のpytestテストを作成・実行する。対応: `NREQ-004-S01`〜`NREQ-004-S03`、設計「試験設計」。完了条件: 表と状態が読め、標準出力JSON一件と終了コードが維持される。

## 4. 文書と品質

- [x] 4.1 `README.md`に新バックボーン、全型番の`train --restart`と閾値確認、`test --restart`、異常結果画像の左右配置、学習時の条件表を記し、正式仕様への同期対象を確認する。対応: `REQ-020`、`REQ-010`、`NREQ-004`、設計「移行とロールバック」。完了条件: 操作と成果物の説明が実装に一致する。
- [x] 4.2 関連pytest、`npm run check`、`npx --no-install openspec validate restore-tv-backbone-and-improve-output --strict`、トレーサビリティ`--phase implementation`を実行し、証跡に環境・コマンド・結果を記録する。対応: 全要件、設計「試験設計」。完了条件: 自動試験・品質検査・参照テスト収集が成功する。

## 5. 対象環境の受け入れ確認

- [ ] 5.1 Ubuntu 24.04 LTSとWindows 11で`tv_in1k`の実重みを用いて学習し、checkpointで検査する。結果を証跡に記録する。対応: `AC-001`、設計「受け入れ検証」。完了条件: 両OSの実行結果で検証済みと判断できる。
- [ ] 5.2 対象の全型番で旧成果物の退避、`train --restart`、閾値・表示範囲の確認、`test --restart`を行い証跡に記録する。対応: `AC-002`、設計「受け入れ検証」。完了条件: 全型番の移行を確認できる。
- [ ] 5.3 両OSの実画像で正常分割の非着色、異常分割の左原画像・右重ね合わせ画像を確認し証跡に記録する。対応: `AC-003`、設計「受け入れ検証」。完了条件: 結果画像とJSONを照合できる。
- [ ] 5.4 両OSの端末・非端末で学習の表、完了・枝刈り・失敗・再開、標準出力JSONと終了コードを確認し証跡に記録する。対応: `AC-004`、設計「受け入れ検証」。完了条件: 試行条件と結果を読み取れる。
- [x] 5.5 verify / archive前にOpenSpec厳密検証とトレーサビリティ`--phase complete`を実行する。実機確認だけが延期される場合はREADMEに未検証のAC-IDとタスク番号を記録し、利用者の明示的な了承後に`--phase limited-archive`を使う。対応: `AC-001`〜`AC-004`、設計「受け入れ検証」。完了条件: 適用する検査が成功し証跡をレビューできる。
