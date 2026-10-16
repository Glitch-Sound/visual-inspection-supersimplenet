## 1. 設定契約と擬似画像生成

- [x] 1.1 `src/app/common/config.py` に `size_px`、`intensity_range`、`images_per_validation_image` の型と範囲検証を追加し、既存の `intensity` と競合する指定を探索前に拒否する。対応: `REQ-030`、設計「データ契約と状態」「境界条件と失敗モード」、`TC-012`〜`TC-015`。完了条件: 旧設定がそのまま読め、不正な境界値は項目と理由を示して拒否される。
- [x] 1.2 `src/app/model_training/synthetic_validation.py` に画素・強度の範囲抽選と画像ごとの複数枚生成を追加する。旧項目のみの場合は乱数列、画像バイト列、出力名を維持する。対応: `REQ-030`、設計「処理フロー」「旧設定と新しい範囲指定」、`TC-012`〜`TC-014`。完了条件: 4種類の欠陥を指定範囲と枚数で同seed再生成でき、原本が不変である。

## 2. 探索結果の選択と利用者への報告

- [x] 2.1 `src/app/model_training/search.py` に擬似 AUROC 用の共通選択処理を追加し、正常完了試行を AUROC 降順、正常p99昇順、試行番号昇順で選ぶ。`normal_percentile` の従来選択を維持する。対応: `REQ-005`、設計「処理フロー」「同点の決定と上限到達の算定」、`TC-001`〜`TC-004`。完了条件: 同点、p99同点、失敗・枝刈り、再開済み試行の選択が決定的である。
- [x] 2.2 `src/app/model_training/cli.py` と `src/app/model_training/artifacts.py` を共通選択処理に合わせ、同じ最良試行で全件再学習・結果保存を行い、AUROC 1.0の正常完了試行数を保存して1件以上なら警告する。p99欠落時は旧成果物を保持して理由を示す。対応: `REQ-005`・`REQ-007`、設計「処理フロー」「インターフェースと失敗時の結果」、`TC-004`・`TC-005`・`TC-010`・`TC-011`。完了条件: CLI表示・実行記録・結果JSONの試行と件数が一致し、旧結果の未記録と新結果の0件を区別できる。

## 3. 結果契約、試験、案内

- [x] 3.1 `src/app/common/contracts.py` の `BestTrialResult` に上限到達件数を追加し、`tests/test_training.py` へ `TC-001`・`TC-002`・`TC-003`・`TC-004`・`TC-005`・`TC-006`・`TC-007`・`TC-008`・`TC-009`・`TC-010`・`TC-011` の pytest テストを実装または既存テストから対応付ける。対応: `REQ-005`・`REQ-007`、設計「データ契約と状態」「試験設計」。完了条件: 設計表の全pytest関数が収集・実行でき、結果読戻し、警告、旧成果物保持、重み再利用、グループ独立を検証する。
- [x] 3.2 `config/part_XX.json` を `synthetic_auroc` と大小の画素範囲・強度範囲・複数枚の初期例に更新し、`README.md` に実画像と残り誤差から平行移動・回転の拡張強度を決める手順、条件変更時の `train --restart`、AUROC警告の扱いを書く。`tests/test_config.py` に `TC-016` の pytest テストを追加する。対応: `REQ-039`、設計「雛形の条件」「移行とロールバック」、`TC-016`。完了条件: 雛形を設定として読め、案内が実測と擬似AUROCの限界を明示する。
- [x] 3.3 `tests/test_synthetic_validation.py` と `tests/test_training.py` に `TC-012`・`TC-013`・`TC-014`・`TC-015` の pytest テストを実装し、旧画像バイト列、複数枚・境界値・同seed再現、不正設定時の旧成果物保持を検証する。対応: `REQ-030`、設計「試験設計」。完了条件: 対応する全pytest関数が成功し、旧経路の回帰が検出できる。

## 4. 対象環境での受け入れ確認

- [ ] 4.1 Ubuntu 24.04 LTSの対象実画像で4種類、大小の画素範囲、強度範囲、複数枚と同seedの再生成・原本不変を確認し、`openspec/changes/archive/2026-10-16-tune-synthetic-validation/evidence/acceptance.md` に環境・条件・結果を記録する。対応: `AC-001`、設計「受け入れ検証」。完了条件: AC-001を実画像の証跡で「検証済み」にできる。
- [ ] 4.2 対象OSで同点選択、AUROC 1.0の件数・警告、旧設定の画像・スコア互換、条件相違時の再開拒否・旧成果物保持を `train` と結果JSONで照合し、同じ証跡に記録する。対応: `AC-002`・`AC-003`・`AC-004`、設計「受け入れ検証」。完了条件: 各AC-IDについて実行条件、試行番号、件数、警告、保持した成果物を読戻せる。
- [ ] 4.3 対象型番の実画像と残り誤差分布を確認し、雛形の範囲と平行移動・回転の拡張強度を運用者が調整できることを案内に沿って確認して証跡に記録する。対応: `AC-005`、設計「受け入れ検証」。完了条件: 初期例の採否、調整内容と理由、未確認の性能条件が記録される。

## 5. 品質・トレーサビリティ

- [x] 5.1 `uv run --locked pytest tests/test_synthetic_validation.py tests/test_training.py tests/test_config.py` と `npm run check` を実行し、format、lint、型検査、全テスト、リポジトリ検査を通す。対応: `REQ-005`・`REQ-007`・`REQ-030`・`REQ-039`、設計「試験設計」「網羅性確認」。完了条件: 全TC-IDの自動試験と品質ゲートが成功し、実行環境・結果を証跡に記録する。
- [x] 5.2 実装後に `uv run --locked python scripts/check_openspec_traceability.py --change tune-synthetic-validation --phase implementation` を実行し、verify / archive 前に `npx --no-install openspec validate tune-synthetic-validation --strict` と通常は `--phase complete` のトレーサビリティ検査を通す。対応: 全要件・`AC-001`〜`AC-005`、設計「網羅性確認」「受け入れ検証」。完了条件: 全Scenarioの参照テストを収集でき、受け入れ状態と証跡が検査に一致する。実機確認だけ延期する場合は未完了の4.1〜4.3をREADMEの「延期中の受け入れ確認」へ引き継ぎ、利用者の明示的な了承後に `--phase limited-archive` を使う。
