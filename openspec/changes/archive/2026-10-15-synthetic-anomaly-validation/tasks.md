## 1. 設定と擬似検証入力

- [x] 1.1 `src/app/common/config.py` と `config/part_XX.json` にグループ別の `objective` と `synthetic_validation` の厳密な契約・既定値を追加し、旧設定の読込みと不正値拒否を確認する。対応: `REQ-030`、設計「データ契約と状態」、`TC-001`, `TC-002`。完了条件: 旧設定は `normal_percentile` で読め、未知種類、空種類、強度範囲外を拒否する。
- [x] 1.2 `src/app/model_training/synthetic_validation.py` に画像ごとの安定 seed による4種類の合成を実装し、検証用一時画像だけを生成する。対応: `REQ-030`、設計「擬似画像の生成と seed」、`TC-001`, `TC-002`。完了条件: 同条件で同じ画像が得られ、正常の元・準備済み画像が不変である。

## 2. 探索と再開

- [x] 2.1 `src/app/model_training/search.py` と `trainer.py` で正常・擬似スコアの取得、AUROC、正常99パーセンタイル、擬似スコア要約、試行 seed の適用を実装する。目的別に minimize / maximize と枝刈り方法を切り替える。対応: `REQ-005`, `REQ-032`, `REQ-030`、設計「処理フロー」「AUROC と枝刈り」「学習と探索の再現条件」、`TC-001`, `TC-005`〜`TC-008`。完了条件: 同条件の目的値再現と、同点・空・非有限スコアを含む自動試験で目的値と失敗状態が一致する。
- [x] 2.2 `src/app/model_training/search.py` と `cli.py` に評価契約の履歴照合、旧履歴の同目的再開、条件不一致時の `--restart` 案内を追加する。対応: `REQ-031`, `REQ-005`、設計「データ契約と状態」「インターフェースと失敗時の結果」、`TC-003`, `TC-004`, `TC-008`。完了条件: 一致時だけ残り試行を実行し、拒否時は完成済み成果物を保持する。

## 3. 結果の保存と試験

- [x] 3.1 `src/app/common/contracts.py`、`src/app/model_training/artifacts.py`、`cli.py` で最良試行の目的名・各指標・擬似条件を保存・表示し、旧結果を未測定として読めるようにする。暫定閾値の算出式は維持する。対応: `REQ-007`, `REQ-005`、設計「データ契約と状態」「移行とロールバック」、`TC-007`, `TC-009`〜`TC-013`。完了条件: 新旧の結果と checkpoint を読み戻せ、保存中断から旧一式を復旧できる。
- [x] 3.2 `tests/test_synthetic_validation.py` に pytest ケース `TC-001`, `TC-002` の `test_req_030_s01`, `test_req_030_s02` を作り、4種類・強度・seed・探索結果の再現・原本不変を確認する。対応: `REQ-030-S01`, `REQ-030-S02`、設計「試験設計」。完了条件: `uv run --locked pytest tests/test_synthetic_validation.py -q` が成功する。
- [x] 3.3 `tests/test_training.py` に pytest ケース `TC-003`, `TC-004`, `TC-005`, `TC-006`, `TC-007`, `TC-008`, `TC-009` を追加し、`test_req_031_s01`, `test_req_031_s02`, `test_req_032_s01`, `test_req_005_s01_synthetic`, `test_req_005_s02_synthetic`, `test_req_005_s03`, `test_req_007_s01_synthetic` を収集・実行する。対応: `REQ-031-S01`, `REQ-031-S02`, `REQ-032-S01`, `REQ-005-S01`〜`S03`, `REQ-007-S01`、設計「試験設計」。完了条件: 指定テストが成功し、旧探索順位と新 AUROC 順位が確認できる。
- [x] 3.4 `tests/test_model_adapter.py` と `tests/test_training.py` の pytest ケース `TC-010`, `TC-011`, `TC-012`, `TC-013` を更新し、`test_group_req_007_s02`〜`test_group_req_007_s05` で重み再利用、保存復旧、不整合拒否、複数グループ独立性を確認する。対応: `REQ-007-S02`〜`S05`、設計「試験設計」。完了条件: 各テストが収集・成功し、新指標を含む結果契約でも既存保証を維持する。
- [x] 3.5 `README.md` の用語集と学習手順に擬似欠陥、擬似 AUROC、目的選択、`--restart` 条件、実異常性能ではない旨を記載する。対応: `REQ-005`, `REQ-031`、設計「移行とロールバック」。完了条件: 設定例と CLI・結果 JSON の名称が一致し、旧設定の扱いが分かる。

## 4. 品質と受け入れ

- [x] 4.1 `uv run --locked pytest`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change synthetic-anomaly-validation --phase implementation` を実行し、全TCの成功・収集結果を `openspec/changes/archive/2026-10-15-synthetic-anomaly-validation/evidence/acceptance.md` に記録する。対応: `REQ-005`, `REQ-007`, `REQ-030`〜`REQ-032`、設計「試験設計」「受け入れ検証」。完了条件: 自動試験・品質検査が成功し、日付・環境・版・コマンド・結果が記録される。
- [ ] 4.2 `AC-001`〜`AC-005` を Ubuntu 24.04 LTS・Windows 11 の対象環境で、正常画像の全・単独グループ学習、4種類の擬似画像、固定 seed の再実行、旧設定、失敗・再開、結果読戻しで検証する。`openspec/changes/archive/2026-10-15-synthetic-anomaly-validation/evidence/acceptance.md` と design の「受け入れ検証」を更新する。対応: `AC-001`〜`AC-005`、設計「受け入れ検証」。完了条件: 各 AC の状態が「検証済み」、残る検証が「なし」となり、対象OS・依存版・使用デバイス・結果を含む実在証跡がある。
- [x] 4.3 verify / archive 前に `npx --no-install openspec validate synthetic-anomaly-validation --strict` とトレーサビリティ検査を実行する。通常は `--phase complete`、実機確認のみ延期する場合は README の「延期中の受け入れ確認」へ未完了タスクと AC-ID を移して `--phase limited-archive` を使う。対応: `AC-001`〜`AC-005`、設計「受け入れ検証」。完了条件: 厳密検証と該当 phase が成功し、延期時は利用者の明示的了承を得る。
