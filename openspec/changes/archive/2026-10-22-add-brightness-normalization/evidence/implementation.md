# 実装・自動検証記録

実施日: 2026-10-22。<br />
実施環境: macOS 27.0.1 arm64、Python 3.13.15 (uv環境)、Node.js v24.18.0、npm 11.16.0。

| コマンド | 結果 |
| --- | --- |
| `uv run --locked pytest tests/test_config.py tests/test_preparation.py -q` | 80件成功 |
| `uv run --locked pytest` | 268件成功。依存ライブラリ由来を含む53件の警告 |
| `npm run check` | OpenSpec全件検証、format、lint、pyright、268件のpytest、リポジトリ検査、進行中changeの実装段階トレーサビリティ検査が成功 |
| `uv run --locked python scripts/check_openspec_traceability.py --change add-brightness-normalization --phase implementation` | 成功。設計の全TC-IDのpytest参照を収集可能 |
| `npx --no-install openspec validate add-brightness-normalization --strict` | 成功 |

試験は設定の既定値・不正値、median・mean、除外範囲、縮小基準の同一分割、倍率上下限、四捨五入・飽和、値なし・対象輝度0、無効化、両準備の指紋、旧manifestの拒否を確認した。<br />
画像保存の試験は実OpenCV・NumPyとPNGを使用し、位置合わせはテストダブルを使用した。<br />
Ubuntu 24.04 LTSとWindows 11の対象実機、実撮影画像、実モデル、GPUによる受け入れ確認は実施していない。<br />
AC-001～AC-005は未検証であり、この記録は運用開始の承認を示さない。
