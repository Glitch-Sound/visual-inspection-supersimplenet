# 自動検証記録

2026-10-12、macOS (Darwin)、Python 3.13.15で確認した。

- `uv run --locked pytest tests/test_group_artifact_names.py tests/test_evaluation.py tests/test_preparation.py tests/test_training.py -q`: 113件成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change pad-group-artifact-names --phase implementation`: 成功。
- `npx --no-install openspec validate pad-group-artifact-names --strict`: 成功。
- `npm run check`: 225件のpytestを含む全検査が成功。

2026-10-12、旧名成果物からの再生成経路を統合テストへ追加した後に再確認した。

- `uv run --locked pytest tests/test_group_artifact_names.py -q`: 12件成功。旧名の学習成果物と現行参照だけがある状態から、学習準備・学習・全件検査を実行し、新名での読戻しを確認。
- `npm run check`: OpenSpec検証、format、lint、型検査、235件のpytest、リポジトリ検査、トレーサビリティ検査が成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change pad-group-artifact-names --phase implementation`: 成功。

この記録はローカルのパスと固定データでの検証である。<br />
Ubuntu 24.04 LTSとWindows 11の対象実機、実画像・実モデルを用いた再生成と読戻しは未実施。
