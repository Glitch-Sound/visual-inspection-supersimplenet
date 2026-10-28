## 1. 設定・画像準備・結果契約

- [x] 1.1 `src/app/image_preparation/imaging.py` と `preparation.py` の `check` 描画を、分割IDから決まる色、画像と範囲の寸法に応じた枠幅・ラベル、ラベルの下地と配置へ変更する。対応: `REQ-001`、設計「描画判断」、`TC-001`、`TC-006`。完了条件: 全画像とグループ画像の同一IDが同色で、座標と元画像が変わらない。
- [x] 1.2 `src/app/common/config.py` と `config/part_XX.json` に `alignment.method` の既定値ORB、方法別 `orb`・`ecc` 設定、NONE、厳格な数値・余分項目検証、正規化設定を含む準備指紋を実装する。対応: `REQ-002`、`REQ-003`、`REQ-025`、`REQ-042`、設計「設定判断」「データ契約と状態」、`TC-012`、`TC-032`～`TC-035`。完了条件: 旧平坦形式と不正値を拒否し、方法・条件の変更で指紋が変わる。
- [x] 1.3 `src/app/image_preparation/imaging.py`・`preparation.py`、`src/app/common/contracts.py`、`src/app/model_evaluation/evaluation.py` にECCの初期探索・制限付き変換・相関判定、NONEの無変形、方法別の準備・検査結果と失敗時の引き継ぎを実装する。対応: `REQ-002`、`REQ-003`、`REQ-025`、`REQ-043`、設計「位置合わせ判断」「処理フロー」「データ契約と状態」、`TC-017`、`TC-018`、`TC-026`、`TC-027`、`TC-036`～`TC-038`。完了条件: 方法別の正常・失敗・省略が記録され、失敗時の学習除外・試験未判定・旧成果物保持を確認できる。

## 2. 自動試験と案内

- [x] 2.1 `tests/test_preparation.py` の `TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`、`TC-006` を追加・更新し、画像寸法、複数ID、重なり、縮小、同一IDの色とラベル、元画像不変を検証する。対応: `REQ-001`、設計「試験設計」「描画判断」。完了条件: 各TCの指定pytest関数が収集・成功する。
- [x] 2.2 `tests/test_preparation.py` の `TC-033`、`TC-034`、`TC-035` を追加し、method省略時ORB、3方法の設定、不正値・旧平坦形式・無関係な条件の拒否と既存成果物保持を検証する。対応: `REQ-042`、設計「試験設計」「設定判断」。完了条件: 各TCの指定pytest関数が収集・成功する。
- [x] 2.3 `tests/test_preparation.py` と `tests/test_test_pre_group.py` の `TC-007`、`TC-008`、`TC-009`、`TC-010`、`TC-011`、`TC-012`、`TC-013`、`TC-014`、`TC-015`、`TC-016`、`TC-017`、`TC-018`、`TC-019`、`TC-020`、`TC-021`、`TC-022`、`TC-023`、`TC-024`、`TC-025`、`TC-026`、`TC-027`、`TC-028`、`TC-029`、`TC-030`、`TC-031`、`TC-032` を追加・更新し、ORB回帰、NONEの画素不変、ECCの既知移動・回転・倍率と失敗、学習除外・試験未判定、グループ間共有、指紋不一致・再準備を検証する。対応: `REQ-002`、`REQ-003`、`REQ-025`、設計「試験設計」「位置合わせ判断」。完了条件: 各TCの指定pytest関数が収集・成功する。
- [x] 2.4 `tests/test_evaluation.py` の `TC-036`、`TC-037`、`TC-038` を追加し、NONEの検査継続、ECC失敗の未判定・再撮影要否、不正記録の推論前拒否と旧結果保持を検証する。対応: `REQ-043`、設計「試験設計」「データ契約と状態」。完了条件: 各TCの指定pytest関数が収集・成功する。
- [x] 2.5 `README.md` の設定・再実行手順と用語集、`config/part_XX.json` の例を新契約に合わせ、旧設定・旧成果物を使わないことと `min_correlation` の設定方法を案内する。対応: `REQ-025`、`REQ-042`、`AC-002`、`AC-005`、設計「移行とロールバック」。完了条件: 3方法と再実行順序が案内され、設定例が読み込める。

## 3. 品質と受け入れ確認

- [x] 3.1 `uv run --locked pre-commit run --all-files`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change improve-check-visuals-and-alignment-options --phase implementation` を実行し、全TCの収集と成功を確認する。対応: `REQ-001`、`REQ-002`、`REQ-003`、`REQ-025`、`REQ-042`、`REQ-043`、設計「試験設計」「網羅性確認」、`TC-001`～`TC-038`。完了条件: 全コマンド成功と対象環境・結果を `openspec/changes/archive/2026-10-28-improve-check-visuals-and-alignment-options/evidence/acceptance.md` に記録する。
- [ ] 3.2 Ubuntu 24.04 LTSとApple silicon macOSで複数・重複分割の `check` 画像を開き、枠・番号・色・同一IDの一致を目視し証跡へ記録する。対応: `AC-001`、設計「受け入れ検証」、`TC-001`～`TC-006`。完了条件: 両環境の画像、表示条件、判読結果を証跡に残し、AC-001を検証済みにする。
- [ ] 3.3 同じ対象環境で型番設定の3方法、ORB既定値、不正値・旧形式の拒否を実CLIで確認し、旧成果物保持を証跡へ記録する。対応: `AC-002`、設計「受け入れ検証」、`TC-033`～`TC-035`。完了条件: 両環境の設定・実行結果と拒否理由を証跡に残し、AC-002を検証済みにする。
- [ ] 3.4 同じ対象環境でORB・ECC・NONEの `train-pre`、`test-pre`、`test` と成果物読戻しを実施し、方法・状態・警告・未判定を証跡へ記録する。対応: `AC-003`、設計「受け入れ検証」、`TC-017`、`TC-018`、`TC-026`、`TC-027`、`TC-036`～`TC-038`。完了条件: 両環境の準備manifestと検査結果を読戻し、AC-003を検証済みにする。
- [ ] 3.5 同じ対象環境で、基準画像と実撮影画像の移動・回転・拡大縮小を含むECC結果を確認し、設定した `min_correlation`、推定変形量、分割位置、失敗例を証跡へ記録する。対応: `AC-004`、設計「受け入れ検証」「位置合わせ判断」、`TC-018`、`TC-027`。完了条件: 実画像の切り出し位置を両環境で確認し、AC-004を検証済みにする。実画像がない間は未検証のままにする。
- [ ] 3.6 同じ対象環境で方法・条件変更後の旧成果物拒否と `check`、`train-pre`、`train`、`test-pre`、`test` の再実行を確認し、結果を証跡へ記録する。対応: `AC-005`、設計「受け入れ検証」「移行とロールバック」、`TC-032`。完了条件: 両環境の再生成と読戻しを証跡に残し、AC-005を検証済みにする。
- [x] 3.7 verify / archive 前に `npx --no-install openspec validate improve-check-visuals-and-alignment-options --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change improve-check-visuals-and-alignment-options --phase complete` を実行し、設計の受け入れ表と証跡内容をレビューする。対象OS・実画像確認だけを延期する場合は未完了の3.2～3.6とAC-IDをREADMEの「延期中の受け入れ確認」へ引き継ぎ、利用者の明示的了承を得てから `--phase limited-archive` を使う。対応: `AC-001`～`AC-005`、設計「受け入れ検証」「網羅性確認」。完了条件: 該当工程のトレーサビリティと厳格検証が成功し、証跡の対象環境・範囲を確認する。
