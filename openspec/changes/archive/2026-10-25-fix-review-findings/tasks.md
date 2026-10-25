## 1. 設定契約と入力エラー

- [x] 1.1 `src/app/common/config.py` で `brightness_normalization` 全体の省略だけを無効扱いにし、子項目の既定値を維持する。グループの旧 `range_ids` 等は項目名と「廃止された項目」を示す入力不備にする。対応: `REQ-021`、`REQ-027`、設計「データ契約と状態」「処理フロー」、`TC-001`〜`TC-008`。完了条件: 設定・準備テストで省略時の画素と指紋、明記時の既定値、旧項目の表示と終了コードを確認できる。
- [x] 1.2 `src/app/common/config.py` の擬似異常端点検証で巨大整数から生じる `OverflowError` を捕捉し、項目名を含む入力不備へ変換する。対応: `REQ-034`、設計「境界条件と失敗モード」、`TC-020`〜`TC-022`。完了条件: 巨大整数の5コマンド入力が未処理例外にならず、既存成果物を更新しない。

## 2. 学習成果物

- [x] 2.1 `src/app/common/contracts.py` と `src/app/model_training/artifacts.py` で、既定値適用後の `synthetic_anomaly` 3範囲を `BestTrialResult` と checkpoint の `visual_inspection` に保存する。対応: `REQ-007`、設計「データ契約と状態」「学習成果物の公開」、`TC-011`〜`TC-016`。完了条件: 両成果物の値が設定と一致し、保存済みJSONとcheckpointを読み戻せる。
- [x] 2.2 `src/app/model_training/search.py`、`cli.py`、`artifacts.py` で `RDBStorage` を明示的に保持し、最良試行と試行数を取得してから接続を閉じ、探索履歴を公開する。失敗経路でも接続を閉じる。対応: `REQ-008`、`REQ-038`、設計「Optuna 接続終了と公開順」、`TC-017`〜`TC-019`、`TC-023`。完了条件: 接続終了が移動より先に行われ、保存先の `study.db` から最良試行を読み戻せる。

## 3. 検査と結果公開

- [x] 3.1 `src/app/common/result_index.py` から `recover_results` と `.backup-` 退避を削除し、旧グループの検証・削除後に完成済み一時グループを移す。`test` の公開前失敗は旧結果を保持し、公開途中失敗後は再実行で作り直す。対応: `REQ-013`、`REQ-028`、設計「検査結果の公開」「境界条件と失敗モード」、`TC-024`〜`TC-034`、`TC-041`〜`TC-042`。完了条件: 退避が作られず、公開前・公開途中・再実行の結果状態を確認できる。
- [x] 3.2 `src/app/model_evaluation/evaluation.py` と `cli.py` で最良試行・checkpoint・型番設定の閾値および擬似異常設定を推論前に照合する。閾値未設定や不一致は `train` からのやり直しを案内する。対応: `REQ-016`、設計「検査契約照合」「インターフェースと失敗時の結果」、`TC-035`〜`TC-040`。完了条件: 新旧成果物2組の混在と未設定値を結果未公開のまま拒否し、再実行方法を表示する。

## 4. 型番単位の一時領域

- [x] 4.1 `src/app/common/cli.py` の型番ロック取得後に共通掃除処理を追加する。既知パターンを `data/03_check`、`data/04_train`、`data/05_test`、`data/06_result`、`optuna`、`weights` の当該型番だけで照合し、全グループの一時領域を削除する。リンクや想定外の種類は拒否する。対応: `REQ-037`、設計「一時領域の整理位置」、`TC-009`〜`TC-010`。完了条件: 5コマンドのどれを開始しても別グループの残骸を消し、別型番・管理対象外・リンク先は保持する。

## 5. 文書と運用手順

- [x] 5.1 `README.md` と正式仕様3件を差分仕様に合わせる。退避・復旧および旧 `generations/` と `current.json` の移行文言を削除し、`REQ-008-S02` の題名から「明示的な再学習」を除く。再実行手順と成果物非互換を明記する。対応: `AC-008`、`REQ-013`、`REQ-008`、設計「移行とロールバック」。完了条件: 文書に旧文言が残らず、現行CLIの振る舞いと一致する。

## 6. 自動試験・品質・受け入れ

- [x] 6.1 `tests/test_config.py`、`tests/test_preparation.py`、`tests/test_training.py`、`tests/test_evaluation.py`、必要な `tests/test_review_findings.py` に、design の `TC-001`〜`TC-042` に対応するテストを追加または更新する。既存テストは変更した契約を確認し、新規テストは輝度省略、両成果物の記録、Optuna 接続終了、5 CLI の掃除、旧項目・巨大整数・閾値未設定、公開失敗と2種類の混在を確認する。対応: `REQ-021`, `REQ-027`, `REQ-037`, `REQ-007`, `REQ-008`, `REQ-034`, `REQ-038`, `REQ-013`, `REQ-016`, `REQ-028`、設計「試験設計」、`TC-001`, `TC-002`, `TC-003`, `TC-004`, `TC-005`, `TC-006`, `TC-007`, `TC-008`, `TC-009`, `TC-010`, `TC-011`, `TC-012`, `TC-013`, `TC-014`, `TC-015`, `TC-016`, `TC-017`, `TC-018`, `TC-019`, `TC-020`, `TC-021`, `TC-022`, `TC-023`, `TC-024`, `TC-025`, `TC-026`, `TC-027`, `TC-028`, `TC-029`, `TC-030`, `TC-031`, `TC-032`, `TC-033`, `TC-034`, `TC-035`, `TC-036`, `TC-037`, `TC-038`, `TC-039`, `TC-040`, `TC-041`, `TC-042`。完了条件: 全TCに実在するpytest関数が対応し、対象テストが成功する。
- [x] 6.2 `uv run --locked pytest`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change fix-review-findings --phase implementation` を実行し、結果・環境・版を `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/verification.md` に記録する。対応: 全差分要件、設計「試験設計」「網羅性確認」。完了条件: 品質チェックが成功し、参照テストが収集できる。
- [ ] 6.3 `AC-001`、`AC-002`、`AC-003`、`AC-004`、`AC-005`、`AC-006`、`AC-007`、`AC-008` を design の「受け入れ検証」の各条件で確認する。Ubuntu 24.04 LTSとWindows 11の対象環境では全5 CLI、成果物読戻し、公開失敗後の再実行、Optuna履歴の移動と読戻しを実施し、環境・Python・依存版・手順・結果を `openspec/changes/archive/2026-10-25-fix-review-findings/evidence/acceptance.md` に記録する。対応: 全AC、設計「受け入れ検証」。完了条件: 各ACの対象環境と証跡をレビューし、確認済みだけを「検証済み」にする。環境を利用できない確認は未検証のまま残す。
- [x] 6.4 verify / archive 前に `npx --no-install openspec validate fix-review-findings --strict` と `uv run --locked python scripts/check_openspec_traceability.py --change fix-review-findings --phase complete` を実行する。対象環境の受け入れ確認だけが延期される場合は `--phase limited-archive` を使い、README の「延期中の受け入れ確認」に change名、AC-ID、状態「未検証」、未完了タスク番号と確認内容を記録する。対応: 全AC、設計「受け入れ検証」。完了条件: 証跡の内容と環境をレビューし、指定phaseの検査に合格する。制限付きアーカイブは利用者の明示的了承後にのみ行う。
