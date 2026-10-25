## 1. 設定と準備契約

- [x] 1.1 `src/app/common/config.py` のグループ設定を必須の `ranges[]` に変更し、各要素の3項目、ID一意性・共通 `range` 参照・値境界、旧グループ項目を全グループについて検証する。エラーにはグループID、分割IDまたは要素位置、理由を含め、既存の5コマンドの入力不備経路へ渡す。対応: `REQ-021`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-001`〜`TC-005`。完了条件: 新形式を読め、旧形式と全違反を成果物更新前に拒否できる。
- [x] 1.2 `src/app/common/config.py` の準備指紋と `src/app/image_preparation/preparation.py` の対象ID・manifestを `ranges[].id` から導出する。閾値・表示範囲は指紋から除く。対応: `REQ-025`、設計「データ契約と状態」「技術判断」、`TC-006`〜`TC-009`。完了条件: 内部 `range_ids` が設定と一致し、検査値だけの変更で指紋が変わらない。

## 2. 学習と検査

- [x] 2.1 `src/app/model_training/cli.py` と `src/app/model_training/artifacts.py` の対象IDを新設定から導出し、最良試行の `range_ids` とグループ単位の暫定閾値書戻しを維持する。対応: `REQ-029`、設計「処理フロー」「データ契約と状態」、`TC-010`〜`TC-012`。完了条件: 対象グループの分割IDと暫定値だけが更新され、各分割の検査条件は保持される。
- [x] 2.2 `src/app/model_evaluation/evaluation.py` で分割IDごとの閾値・出どころ・表示範囲を選択し、判定と異常画像へ適用する。checkpoint・最良試行の暫定閾値照合、元画像集約、公開前失敗時の旧結果保全を維持する。対応: `REQ-010`、`REQ-018`、`REQ-019`、設計「処理フロー」「技術判断」、`TC-013`〜`TC-016`、`TC-023`〜`TC-030`。完了条件: 混在する分割条件と境界値で画像・判定・出どころが一致する。
- [x] 2.3 `src/app/common/contracts.py` と検査結果の生成箇所で、グループ直下の旧 `threshold`・`heatmap_range` を廃止し、各分割に `threshold`・`threshold_source`・`heatmap_range` を必須として記録・検証する。未判定・分割エラーにも使用予定値を残す。対応: `REQ-012`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-017`〜`TC-022`。完了条件: 新形式JSONを読み戻せ、欠落・旧形式を拒否できる。
- [x] 2.4 `src/app/model_evaluation/cli.py` の開始表示をグループID・分割ID別の閾値と `provisional` / `configured` に変える。対応: `REQ-036`、設計「インターフェースと失敗時の結果」、`TC-031`。完了条件: 表示値と結果JSONが一致し、標準出力の実行記録を変えない。

## 3. 自動試験

- [x] 3.1 `tests/test_config.py` と必要な共通fixtureへ新形式を反映し、5コマンド共通の設定拒否、同一IDのグループ間共有、旧項目、欠落・不正値、旧成果物保全をpytestで検証する。対応: `REQ-021`、設計「試験設計」、`TC-001`、`TC-002`、`TC-003`、`TC-004`、`TC-005`。完了条件: 設計に記載した5つのpytest実装先を含む関連テストが成功する。
- [x] 3.2 `tests/test_config.py`、`tests/test_preparation.py`、`tests/test_evaluation.py` に、導出ID、manifest・指紋、検査値変更後の `test` のみの再実行をpytestで検証する。対応: `REQ-025`、設計「試験設計」、`TC-006`、`TC-007`、`TC-008`、`TC-009`。完了条件: 4つのpytest実装先で準備・学習成果物の不変と新結果を確認できる。
- [x] 3.3 `tests/test_training.py` に、対象グループの書戻し、検査条件保持、詳細不備、書戻し失敗をpytestで検証する。対応: `REQ-029`、設計「試験設計」、`TC-010`、`TC-011`、`TC-012`。完了条件: 3つのpytest実装先が成功し、最良試行の内部IDを照合できる。
- [x] 3.4 `tests/test_evaluation.py` と `tests/test_config.py` に、正常・異常画像、同値同色と端色、null・指定閾値・0/1境界、暫定値不一致、分割別表示範囲のpytest検証を追加する。対応: `REQ-010`、`REQ-018`、`REQ-019`、設計「試験設計」、`TC-013`、`TC-014`、`TC-015`、`TC-016`、`TC-023`、`TC-024`、`TC-025`、`TC-026`、`TC-027`、`TC-028`、`TC-029`、`TC-030`。完了条件: 12のpytest実装先が成功し、分割別の判定と画像を照合できる。
- [x] 3.5 `tests/test_results.py` と `tests/test_evaluation.py` に、分割別JSON、未判定・エラー、旧契約拒否、同stem、manifest拒否、複数グループ分離、開始表示をpytestで検証する。対応: `REQ-012`、`REQ-036`、設計「試験設計」、`TC-017`、`TC-018`、`TC-019`、`TC-020`、`TC-021`、`TC-022`、`TC-031`。完了条件: 7つのpytest実装先が成功し、表示と保存値の一致を確認できる。

## 4. 設定例と案内

- [x] 4.1 `config/part_XX.json` の全グループを `ranges[]` に変更し、各分割の `inspection_threshold: null` と `heatmap_range: {"min": 0.0, "max": 1.0}` を明示する。`README.md` の用語集・設定表・結果説明を新形式に合わせ、旧成果物を引き継がない全工程の再実行と、検査値のみ変更時の `test` 再実行を案内する。対応: `AC-005`、`AC-006`、設計「データ契約と状態」「移行とロールバック」。完了条件: 設定例が読め、READMEとJSON項目・運用手順が一致する。

## 5. 品質確認と受け入れ

- [x] 5.1 廃止したグループ項目を前提とするテストを更新・削除し、`npm run check`、`npx --no-install openspec validate per-range-threshold-and-heatmap --strict`、`uv run --locked python scripts/check_openspec_traceability.py --change per-range-threshold-and-heatmap --phase implementation` を実行して結果を change 内の証跡に記録する。対応: `REQ-021`、`REQ-025`、`REQ-029`、`REQ-010`、`REQ-012`、`REQ-018`、`REQ-019`、`REQ-036`、設計「試験設計」「受け入れ検証」、`TC-001`〜`TC-031`。完了条件: 全自動試験・品質検査・参照試験収集が成功する。
- [ ] 5.2 Ubuntu 24.04 LTSとWindows 11の対象実機で、CPUと利用可能なGPUについて新形式の全工程、全件・単独グループ、設定値だけを変えた再検査、不正設定の5コマンド拒否、結果画像・JSON・開始表示の読戻しを行う。`openspec/changes/per-range-threshold-and-heatmap/evidence/acceptance.md` に日付、OS・Python・依存版、デバイス、コマンド、設定条件、結果、制約を記録し、設計「受け入れ検証」を更新する。対応: `AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005`、`AC-006`、設計「受け入れ検証」。完了条件: 全AC-IDを対象環境で確認し、各条件の状態を「検証済み」、残る検証を「なし」にできる。
- [x] 5.3 verify / archive 前に `npx --no-install openspec validate per-range-threshold-and-heatmap --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change per-range-threshold-and-heatmap --phase complete` を実行する。対象実機だけが利用できない場合は、実装・自動試験・品質確認の完了後に `README.md` の「延期中の受け入れ確認」に change名、全未検証AC-ID、未完了タスク5.2と確認内容を記録し、延期と残るリスクについて利用者の明示的な了承を得てから `--phase limited-archive` を実行する。対応: `AC-001`〜`AC-006`、設計「受け入れ検証」「移行とロールバック」。完了条件: 通常の完了検査、または了承済みの制限付き検査と厳密検証が成功する。
