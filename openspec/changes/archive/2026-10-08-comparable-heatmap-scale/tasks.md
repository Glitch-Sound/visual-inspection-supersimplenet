## 1. 表示範囲の設定契約

- [x] 1.1 `src/app/common/config.py`、`config/part_XX.json`、`tests/fixtures/model_config.json` に `heatmap_range.min/max` の設定契約と例を追加する。有限数値、真偽値拒否、`min < max` を検証し、学習・画像準備では省略可能、検査では必須とする。対応: `REQ-019`、設計「データ契約と状態」「判断 1」、`TC-001`、`TC-002`。完了条件: 0〜1 外の値を受理し、無効値と未指定の検査を推論前に拒否できる。
- [x] 1.2 `tests/test_config.py` と `tests/test_evaluation.py` に `TC-001`、`TC-002` の自動テストを追加する。未指定、片側欠落、非数値、真偽値、非有限、同値・逆順、0〜1 外の有効値を試す。対応: `REQ-019` / `REQ-019-S01` / `REQ-019-S02`、設計「試験設計」、`TC-001`、`TC-002`。完了条件: 設計記載の pytest 関数が成功し、エラー時に推論と新結果保存がない。`test --restart` による旧結果の保持は試験条件にしない。

## 2. 共通尺度の可視化

- [x] 2.1 `src/app/model_evaluation/evaluation.py` で型番別表示範囲を全分割へ渡し、異常画像の `anomaly_map` をリサイズ後に範囲へ切り詰め、固定の色番号へ線形変換する。正常画像の保存と `pred_score >= threshold` 判定は保持する。対応: `REQ-010`、設計「処理フロー」「判断 2」、`TC-003`、`TC-004`、`TC-005`、`TC-006`。完了条件: 異なる画像極値でも同じ値が同じヒートマップ色となり、正常画像と判定が変わらない。
- [x] 2.2 `tests/test_evaluation.py` の `TC-003`、`TC-004`、`TC-005` の pytest テストを新しい入力契約に合わせ、`TC-006` の固定画像・異常マップの pytest テストを追加する。対応: `REQ-010` / `REQ-010-S01` / `REQ-010-S02` / `REQ-010-S03` / `REQ-010-S04`、設計「試験設計」、`TC-003`、`TC-004`、`TC-005`、`TC-006`。完了条件: 正常画像の画素一致、ヒートマップ層の共通色と端色、スコア・閾値・判定の不変を確認できる。重ね合わせ後の画素一致は要求しない。

## 3. 結果契約と読戻し

- [x] 3.1 `src/app/common/contracts.py` と `src/app/model_evaluation/evaluation.py` に、元画像単位の結果 JSON の必須 `heatmap_range` と使用値の記録を追加する。未判定や分割エラーを含む結果にも同じ値を保存する。対応: `REQ-012`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-007`、`TC-008`、`TC-009`、`TC-010`。完了条件: 正しい範囲を保存・読戻しでき、欠落・不正な範囲を拒否する。
- [x] 3.2 `tests/test_evaluation.py`、`tests/test_results.py`、`tests/test_platform_smoke.py` の結果生成を新契約へ合わせ、`TC-007`、`TC-008` の pytest テストを追加し、`TC-009` を再実行する。`TC-010` は `tests/test_evaluation.py` に検査入口を通る pytest テストを追加し、型番不一致、危険なパス、重複・参照不整合を含む manifest で推論前に拒否し、結果領域と領域外ファイルに変更がないことを確認する。対応: `REQ-012` / `REQ-012-S01` / `REQ-012-S02` / `REQ-012-S03` / `REQ-012-S04`、設計「試験設計」、`TC-007`、`TC-008`、`TC-009`、`TC-010`。完了条件: 設計記載の pytest 関数が成功し、保存 JSON の範囲、旧形式の拒否、不正 manifest の推論前拒否と領域外アクセスなしを確認できる。

## 4. 案内・品質・受け入れ

- [x] 4.1 `README.md` の用語集・型番設定・検査結果の案内へ表示範囲、モデル同一性の運用確認、元画像との重ね合わせによる色の見え方、モデル更新時の見直し、`test --restart` による旧結果削除と再生成を記載する。`npm run check`、`npx --no-install openspec validate comparable-heatmap-scale --strict`、設計段階と `--phase implementation` のトレーサビリティ検査を実行し、`openspec/changes/archive/2026-10-08-comparable-heatmap-scale/verification.md` にコマンド・日付・環境・結果を記録する。対応: `REQ-019`、`REQ-010`、`REQ-012`、設計「移行とロールバック」「受け入れ検証」、`TC-001`〜`TC-010`。完了条件: 案内と実装が一致し、品質検査と参照テスト収集が成功する。
- [ ] 4.2 `AC-001` を Ubuntu 24.04 LTS・Windows 11 の実モデルで確認する。同一学習済みモデルと表示範囲を運用で照合し、異なる異常マップの同値同色と範囲外の端色をヒートマップ層で確認する。元画像へ重ねた最終画素の一致は求めない。モデル確認方法、結果画像・JSON、コマンド、環境、日付と制約を `verification.md` に記録し、design の受け入れ検証を更新する。完了条件: 両 OS の証跡をレビューでき、残る検証が「なし」、状態が「検証済み」である。
- [ ] 4.3 `AC-002` を Ubuntu 24.04 LTS・Windows 11 の実画像で確認する。正常画像への非着色、異常画像への着色、表示範囲変更時の `pred_score`・閾値・判定の独立性を確認する。結果画像・JSON、コマンド、環境、日付と制約を `verification.md` に記録し、design の受け入れ検証を更新する。完了条件: 両 OS の証跡をレビューでき、残る検証が「なし」、状態が「検証済み」である。
- [ ] 4.4 `AC-003` を Ubuntu 24.04 LTS・Windows 11 で確認する。表示範囲の変更後に `test --restart` で再生成し、前後の結果 JSON から範囲の違いを確認する。結果画像・JSON、コマンド、環境、日付と制約を `verification.md` に記録し、design の受け入れ検証を更新する。完了条件: 両 OS の証跡をレビューでき、残る検証が「なし」、状態が「検証済み」である。
- [ ] 4.5 `AC-004` を Ubuntu 24.04 LTS・Windows 11 の CLI で確認する。表示範囲の未指定と不正値が推論前に理由付きで拒否され、新結果が作られないことを確認する。終了記録・結果領域、コマンド、環境、日付と制約を `verification.md` に記録し、design の受け入れ検証を更新する。完了条件: 両 OS の証跡をレビューでき、残る検証が「なし」、状態が「検証済み」である。
- [x] 4.6 verify / archive 前に `npx --no-install openspec validate comparable-heatmap-scale --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change comparable-heatmap-scale --phase complete` を実行する。実機確認だけを延期して制限付きでアーカイブする場合は、README の引き継ぎと利用者の明示的な了承を確認し、`--phase limited-archive` を使用する。完了条件: 適用する工程の検査が成功し、証跡内容と対象環境をレビューできる。
