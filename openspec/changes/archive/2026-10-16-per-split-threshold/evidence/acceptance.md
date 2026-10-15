# 自動検証記録

実施日: 2026-10-16 (Asia/Tokyo)。<br />
環境: macOS 26.6.2 arm64、Python 3.13.15、pytest 9.1.1。<br />
Ubuntu 24.04 LTSおよびWindows 11の実機・実画像による受け入れ確認は未実施である。

## 実行結果

| コマンド | 結果 | 検証範囲 |
| --- | --- | --- |
| `uv run --locked pytest` | 296件成功 | 既存機能と分割ID別の算出・代替・上書き・結果契約をテストダブルと小規模フィクスチャで確認 |
| `npm run check` | 成功 | OpenSpec全件厳密検証、format、lint、型検査、296件のpytest、リポジトリ検査、実装段階トレーサビリティ検査 |
| `uv run --locked python scripts/check_openspec_traceability.py --change per-split-threshold --phase implementation` | 成功 | 全Scenarioの参照試験を収集可能と確認。テストの成功とは別に実施 |
| `npx --no-install openspec validate per-split-threshold --strict` | 成功 | changeの差分仕様と成果物の形式を確認 |
| `uv run --locked python scripts/check_openspec_traceability.py --change per-split-threshold --phase limited-archive` | 成功 | 対象OSの受け入れ確認だけを未検証としてREADMEへ引き継ぎ、他のタスクと証跡の整合を確認 |
| `git diff --check` | 成功 | 差分の空白エラーなし |

## 受け入れ条件への対応

| AC-ID | 自動検証で確認した内容 | 残る検証・状態 |
| --- | --- | --- |
| AC-001 | グループ単位の閾値算出と判定の既定互換、手動値の扱い | Ubuntu・Windowsの実画像での照合。未検証 |
| AC-002 | 分割ID別のパーセンタイル・マージン・上限、0件時のグループ代替、警告と3成果物への記録 | 両OSの実スコア再計算。未検証 |
| AC-003 | 分割ID別の手動上書き、境界値、学習由来の値の不変性 | 両OSの実画像での判定。未検証 |
| AC-004 | 結果JSONの適用値と由来、異常優先集約、推論失敗時の未判定 | 両OSの結果JSON読戻し。未検証 |
| AC-005 | 不正設定、学習成果物不整合の拒否と現行結果の保持 | 対象環境での拒否結果と旧結果読戻し。未検証 |
| AC-006 | 自動試験では対象OSの実画像を使用していない | Ubuntu 24.04 LTS・Windows 11の実機確認。未検証 |

## 制約

学習器と推論器の一部をテストダブルに置換している。<br />
この記録は対象OSの実重み・実画像による閾値の妥当性、検出性能、誤検出率、本番利用の承認を示さない。
