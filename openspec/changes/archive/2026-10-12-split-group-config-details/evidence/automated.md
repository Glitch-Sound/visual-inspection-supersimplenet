# 自動検証記録

2026-10-12、macOS 26.6.2、Python 3.13.15で確認した。

- `uv run --locked pytest tests/test_config.py tests/test_preparation.py tests/test_training.py tests/test_evaluation.py tests/test_runtime.py -q`: 135件成功。
- `npm run check`: OpenSpec検証、format、lint、型検査、リポジトリ検査、対応検査および234件のpytestが成功。
- `uv run --locked python scripts/check_openspec_traceability.py --change split-group-config-details --phase implementation`: 成功。
- `npx --no-install openspec validate split-group-config-details --strict`: 成功。
- `uv run --locked python -c 'from pathlib import Path; from app.common.config import load_model_config; c = load_model_config(Path("config/part_XX.json")); print(c.groups[0].id, c.groups[0].optuna_settings.execution.trials)'`: `0 10`を出力し、配布雛形の読込を確認。

対象OSの実画像・実モデルによる一連の実行は未実施。<br />
自動試験は設定契約、書戻し、既存の画像準備・学習・検査の回帰を確認する。
