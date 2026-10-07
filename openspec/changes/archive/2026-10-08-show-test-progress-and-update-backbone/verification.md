# 検証記録

## 自動試験と品質確認

- 実施日: 2026-10-08 (JST)
- 環境: macOS 26.6.2 / arm64、Python 3.13.15、Anomalib 2.6.2、timm 1.0.30。
- コマンド: `npm run check`。
- 結果: OpenSpec全件の厳密検証、Ruff format / lint、Pyright、pytest 217件、リポジトリ検査、進行中changeの実装段階トレーサビリティ検査が成功した。
- `TC-001`: `tests/test_training.py::test_model_adapter_uses_racm_backbone`で新しい重み識別子を`pretrained=True`として要求すること、実重みの取得を抑えた状態でAnomalib SuperSimpleNetの特徴抽出器を構築できることを確認した。重みの実ダウンロードと学習は確認していない。
- `TC-002`: 旧探索領域とcheckpointの削除、空の新規Optuna study生成、元画像・設定・事前学習キャッシュの保持を確認した。
- `TC-003`から`TC-006`: 端末バー、非端末の件数と標準出力JSON一件、未判定・分割エラーの処理済み件数、全体失敗時の進捗停止をテストダブルと固定manifestで確認した。

## 残る受け入れ確認

- `AC-001`、`AC-002` / タスク4.1・4.2: Ubuntu 24.04 LTS・Windows 11での端末・非端末表示、実画像を使う未判定・個別エラー・全体失敗と終了状態の確認は未検証。
- `AC-003`、`AC-004` / タスク4.3・4.4: 実重みの取得、対象の全型番の`train --restart`とcheckpoint検査、暫定閾値・ヒートマップ表示範囲の見直し、`test --restart`による再生成は未検証。
- この作業環境に対象型番の元画像・準備済み画像とUbuntu 24.04 LTS・Windows 11の実機がないため、上記の確認を実施できない。自動試験の成功をこれらの受け入れ完了として扱わない。
