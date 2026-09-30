## 1. 基盤とデータ契約

- [ ] 1.1 `pyproject.toml`、`src/app/cli.py`、`src/app/schemas.py` に外観検査用のCLI入口、設定モデル、画像・分割・スコア・結果状態の型を追加する。対応: `REQ-001`、`NREQ-002`、設計「Component Map」。完了条件: `--model XX`を受け取る入口と`normal`、`anomaly`、`undetermined`、`error`の状態型が定義され、既存テストを壊さない。
- [ ] 1.2 `src/app/config.py` にINI/JSONの読み込みと、正方形サイズ、重複ID、負座標、Optuna、データ拡張、ORB設定の検証を実装する。対応: `REQ-001`、設計「State and Data Design」。完了条件: 有効設定を内部モデルへ変換し、不正設定を項目名付きエラーにする。
- [ ] 1.3 `src/app/filename.py` に元画像stemと2桁0埋め分割IDから`stem_nn.png`を生成・解析する契約を実装する。対応: `REQ-003`、`REQ-011`、設計「分割画像名」。完了条件: 学習・試験の分割画像から元画像stemと分割IDを正しく復元できる。
- [ ] 1.4 `src/app/logging.py` と`src/app/device.py` に処理時間、型番、生成物、警告、エラー、GPU/CPU選択を記録する共通処理を追加する。対応: `NREQ-001`、`NREQ-002`、設計「Security, Performance, and Operations」。完了条件: GPUなしをCPUへ切り替え、成功・失敗の要約を同一形式で出力できる。

## 2. 画像準備

- [ ] 2.1 `src/app/alignment.py` にORB位置合わせ、最低マッチ数20、インライア比率0.5、失敗理由を返す処理を追加する。対応: `REQ-005`、設計「Decision: 位置合わせ失敗は学習除外、試験未判定とする」。完了条件: 成功時に変換済み画像と品質値、失敗時に理由を返す。
- [ ] 2.2 `src/app/visualize.py` と`src/app/prepare.py` に、OpenCV座標（左上原点、右向きx、下向きy、右端・下端非包含）で正方形範囲を検証・描画・切り出す処理を追加する。対応: `REQ-002`、`REQ-003`、設計「Processing Flow」2〜5。完了条件: `check`の確認画像と、範囲内の`SIZE x SIZE`画像が出力され、範囲外は出力せずエラーになる。
- [ ] 2.3 `src/app/prepare.py` に学習用ブラックリスト適用、ORB失敗時の学習除外と警告、試験用失敗時の未判定記録を実装する。対応: `REQ-004`、`REQ-005`、設計「準備マニフェスト」。完了条件: 学習対象の除外と試験対象の状態が元画像単位で区別される。
- [ ] 2.4 `src/app/manifest.py` に`data/05_test/XX/_preparation.json`の読み書きを追加し、元画像、分割画像、状態、位置合わせ品質、警告、エラーを記録する。対応: `REQ-005`、`REQ-011`、`REQ-014`、設計「State and Data Design」。完了条件: `test-pre`の未判定状態を`test`が読み取れる。
- [ ] 2.5 `src/app/cli.py` の`check`、`train-pre`、`test-pre`から画像準備サービスを呼び出し、`data/03_check/XX.png`、`data/04_train/XX/`、`data/05_test/XX/`へ出力する。対応: `REQ-002`、`REQ-003`、`REQ-011`。完了条件: 3コマンドが型番引数で実行でき、処理結果と失敗内容をログに出す。

## 3. データセットと学習

- [ ] 3.1 `src/app/dataset.py` に分割画像を元画像stemでグループ化し、seed 42で80%/20%に分割する処理を追加する。対応: `REQ-006`、`NREQ-003`、設計「元画像単位で学習と検証を分割する」。完了条件: 同じstemの分割画像がtrain/validationをまたがず、同じ入力で同じ分割になる。
- [ ] 3.2 `src/app/augmentation.py` に、学習時だけ平行移動、回転、明るさ、コントラスト、色温度、ガンマ、ノイズ、ぼかしを設定単位で適用し、validation/testでは無効にする処理を追加する。対応: `REQ-007`、設計「Decision: 1モデルで全分割IDを処理する」。完了条件: 元ファイルを変更せず、拡張画像を永続化せず、評価入力へ拡張が入らない。
- [ ] 3.3 `src/app/model_adapter.py` に、外部モデル実装を隠蔽する学習・推論・ヒートマップの内部契約を追加する。対応: `REQ-008`、`REQ-009`、`REQ-012`、`REQ-014`、設計「Decision: 外部モデル実装をアダプターで隔離する」。完了条件: 全分割IDを同一モデルへ渡せ、スコア・ヒートマップ・学習済み成果物を内部型で返せる。
- [ ] 3.4 `src/app/threshold.py` に、学習用正常画像のスコア99パーセンタイルを型番閾値へ変換する処理を追加する。対応: `REQ-009`、`REQ-012`、設計「Decision: 正常画像初期評価は99パーセンタイルで行う」。完了条件: 入力スコア列から同一の閾値を再計算でき、空データはエラーになる。

## 4. Optunaと成果物

- [ ] 4.1 `src/app/optimization.py` に学習率、バッチサイズ、エポック数、特徴抽出層、前処理条件の探索空間、seed 42、50試行、99パーセンタイル目的値を実装する。対応: `REQ-008`、`REQ-010`、設計「Processing Flow」7〜9。完了条件: 最小目的値のtrialが選択され、探索条件と評価値を取得できる。
- [ ] 4.2 `src/app/optimization.py` に`optuna/XX/study.db`のSQLite保存、既存studyの再開、既存trial保持を実装する。対応: `REQ-010`、設計「Interfaces and Error Handling」。完了条件: 再実行で既存trialが消えず、未完了試行を継続できる。
- [ ] 4.3 `src/app/training.py` と`src/app/artifacts.py` に、最良試行の学習、`weights/XX.ckpt`、型番metadata、閾値、探索条件、対応する評価値の保存を追加する。対応: `REQ-009`、`NREQ-003`。完了条件: checkpointとmetadataからモデル、閾値、seed、best paramsを一意に復元できる。
- [ ] 4.4 `src/app/cli.py` の`train`からデータ分割、データ拡張、モデルアダプター、Optuna、成果物保存を順序どおりに呼び出す。対応: `REQ-006`〜`REQ-010`。完了条件: 正常画像のみの探索を型番指定で開始・完了できる。

## 5. 推論と結果保存

- [ ] 5.1 `src/app/inference.py` に学習済みパラメータと型番閾値を読み込み、分割画像スコアを`normal`または`anomaly`へ変換する処理を追加する。対応: `REQ-012`。完了条件: 閾値以上が`anomaly`、閾値未満が`normal`となる。
- [ ] 5.2 `src/app/aggregation.py` に元画像stem単位の結果集約を追加し、異常優先、全正常時normal、未判定残存時undeterminedの規則を実装する。対応: `REQ-013`、`REQ-014`。完了条件: 分割結果の組み合わせごとに元画像状態が仕様どおりになる。
- [ ] 5.3 `src/app/results.py` に結果画像、異常ヒートマップ、元画像単位JSONを保存する処理を追加する。対応: `REQ-014`、設計「State and Data Design」。完了条件: JSONに元画像、型番、モデル、閾値、分割、score、判定、日時、位置合わせ、警告、エラーが入り、未判定scoreはnullになる。
- [ ] 5.4 `src/app/cli.py` の`test`から準備マニフェスト、推論、集約、結果保存を呼び出し、ORB失敗を含む試験を完了できるようにする。対応: `REQ-012`〜`REQ-014`、`NREQ-001`〜`NREQ-002`。完了条件: `data/06_result/XX/`に結果画像とJSONが出力され、未判定が消失しない。

## 6. 自動テスト

- [ ] 6.1 `tests/test_config.py` にTC-001、TC-002を実装し、有効設定の変換と不正範囲の拒否をpytestで検証する。対応: `REQ-001`。完了条件: `uv run --locked pytest tests/test_config.py`が成功する。
- [ ] 6.2 `tests/test_prepare.py` にTC-003、TC-004、TC-005、TC-006、TC-015を実装し、確認画像、学習/試験分割、範囲外、ブラックリスト、試験準備を検証する。対応: `REQ-002`〜`REQ-004`、`REQ-011`。完了条件: `uv run --locked pytest tests/test_prepare.py`が成功する。
- [ ] 6.3 `tests/test_alignment.py` にTC-007、TC-008を実装し、学習除外・警告と試験未判定マニフェストを検証する。対応: `REQ-005`。完了条件: `uv run --locked pytest tests/test_alignment.py`が成功する。
- [ ] 6.4 `tests/test_dataset.py`、`tests/test_augmentation.py` にTC-009、TC-010、TC-011、TC-022を実装し、元画像単位split、seed再現、学習時拡張、評価時無効を検証する。対応: `REQ-006`、`REQ-007`、`NREQ-003`。完了条件: 対応pytestが成功し、入力ファイルのハッシュが変わらない。
- [ ] 6.5 `tests/test_optimization.py`、`tests/test_training.py` にTC-012、TC-013、TC-014のpytestテストを作成・実行し、目的値、成果物、SQLite再開を検証する。対応: `REQ-008`〜`REQ-010`。完了条件: 小規模なスタブモデルで探索を完了し、既存trial保持を確認できる。
- [ ] 6.6 `tests/test_inference.py`、`tests/test_aggregation.py`、`tests/test_results.py` にTC-016、TC-017、TC-018、TC-019を実装し、閾値判定、元画像集約、ヒートマップ、JSON、未判定を検証する。対応: `REQ-012`〜`REQ-014`。完了条件: 対応pytestが成功し、状態値とnull scoreが仕様どおりになる。
- [ ] 6.7 `tests/test_device.py`、`tests/test_cli.py` にTC-020、TC-021を実装し、GPUなしのCPU切替とCLIログ要約を検証する。対応: `NREQ-001`、`NREQ-002`。完了条件: GPU検出をモックしたpytestとCLI実行が成功する。

## 7. 品質・運用確認

- [ ] 7.1 `README.md` または利用者向け運用文書に、設定ファイル作成、画像配置、5つのCLIの実行順、生成物、再開方法、未判定の扱いを追記する。対応: `NREQ-002`、設計「Migration and Rollback」。完了条件: 空の雛形から型番指定の運用手順を追跡できる。
- [ ] 7.2 `uv run --locked ruff format --check .`、`uv run --locked ruff check .`、`uv run --locked pyright`、`uv run --locked pytest`、`npm run check`を実行し、既存テストを含む全品質検査を通過させる。対応: 全要件、全TC。完了条件: 全コマンドが終了コード0になる。
- [ ] 7.3 `uv run --locked python scripts/check_openspec_traceability.py --change visual-inspection` と`npx --no-install openspec validate visual-inspection --strict`を実行し、proposal、spec、design、tasks、実装テストの対応漏れがないことを確認する。対応: 全要件、全TC。完了条件: 両コマンドが終了コード0になる。
