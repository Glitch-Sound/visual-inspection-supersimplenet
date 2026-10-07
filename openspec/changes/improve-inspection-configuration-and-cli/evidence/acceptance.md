# 受け入れ確認と品質検査

2026-10-07、macOS 26.6.2 arm64、Python 3.13.15で確認した。
対象の Ubuntu 24.04 LTS と Windows 11、および運用画像・旧成果物での確認は実施していない。

## 自動試験と品質検査

- `uv run --locked pytest -q`: 188件成功。
- `npm run check`: 成功。OpenSpec全件検証、ruff format・lint、pyright、pytest 188件、リポジトリ検査、進行中changeの実装段階トレーサビリティ検査を含む。
- `uv run --locked python scripts/check_openspec_traceability.py --change improve-inspection-configuration-and-cli --phase implementation`: 成功。参照テストを収集可能。
- `npx --no-install openspec validate improve-inspection-configuration-and-cli --strict`: 成功。
- `git diff --check`: 成功。

5 CLI入口の標準出力JSONと人向け段階表示、Rich進捗バーのTTY表示、非TTYの件数表示を自動試験で確認した。
分割推論エラーを記録してコマンドが完了する場合も、標準エラー出力に対象と理由、終了要約に一部エラー件数が表示されることを確認した。
確認画像では`x = 400`と`x = 401`が縮小後の`x = 200`と`x = 201`の矩形と分割IDに対応した。

## AC-001 と AC-002

`tests/test_evaluation.py` の `test_change_req_018_01`〜`test_change_req_018_06`、`tests/test_config.py` の `test_inspection_threshold_is_preserved_when_training_threshold_changes` を実行した。
未指定・`null`では暫定閾値0.5、指定値0.2では指定値、境界値0と1では各指定値が結果JSONの`threshold`に保存されることを確認した。
スコアが閾値と等しい場合は`anomaly`になった。
不正値は`inspection_threshold`の入力不備として拒否され、検査結果は作成されなかった。
checkpoint側の暫定閾値が型番設定と不一致のときは拒否され、既存の最良試行契約テストも成功した。
学習の暫定閾値更新後も検査用閾値0.25が保持された。

AC-002の固定入力による自動検証は完了した。
AC-001の対象OSと実モデルを用いた受け入れ確認は未実施である。

## AC-003〜AC-006 の残る確認

AC-003: Ubuntu 24.04 LTSとWindows 11の実機で5 CLI、進捗、標準出力JSON、終了コードを確認する。
AC-004: 対象型番の実際の基準画像で座標と切り出し位置・`SIZE`を照合する。
AC-005: 対象環境で設定不備、位置合わせ失敗、途中処理失敗、旧成果物保全、未判定を確認する。
AC-006: 旧座標と旧分割画像を対象型番で比較し、必要な再学習と検査結果の再生成、旧成果物の退避を確認する。
これらは自動試験の成功をもって完了扱いにしない。
