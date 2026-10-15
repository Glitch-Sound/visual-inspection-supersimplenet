# alinment-robustness 実装・自動試験証跡

- 実施日: 2026-10-16 (Asia/Tokyo)
- 環境: macOS (Darwin)、Python 3.13.15、OpenCV 5.0.0、NumPy 2.5.3、Pydantic 2.13.4
- コマンド: `npm run check`
- 結果: OpenSpec厳密検証、ruff format、ruff lint、pyright、pytest、リポジトリ検査、全進行中changeの`--phase implementation`トレーサビリティ検査が成功。pytestは312件成功。
- 追加の実処理確認: 決定的なランダム画像を7px右・4px下へ移し、OpenCVの実推定で`similarity`位置合わせを実行。マッチ数1375、インライア比率0.9993、再投影RMSE 0.4862px、出力256×256×3を確認。対応する自動試験は`tests/test_imaging_core.py::test_alignment_similarity_with_real_estimator`。
- 文書レビュー: `config/part_XX.json`と`README.md`の設定名・既定値・誤差の単位・再実行順序が実装と一致することを確認。
- 制約: 対象OSのUbuntu 24.04 LTSとWindows 11での実画像・モデルによる受け入れ確認は未実施。AC-001〜AC-006の状態は未検証のまま。
