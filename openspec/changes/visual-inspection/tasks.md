## 1. 契約・実行基盤

- [ ] 1.1 `pyproject.toml` と `uv.lock` に Python 3.13向けの Anomalib 2.6.2、PyTorch 2.13.0、torchvision 0.28.0、CUDA 13.0用プラットフォーム別source、Optuna、OpenCV headlessを追加し、`check`、`train-pre`、`train`、`test-pre`、`test` のconsole scriptを登録する。対応: `NREQ-001`、設計「背景・前提」「判断 1」「判断 3」、`TC-029`、`TC-030`。完了条件: `uv lock --check` と `uv sync --locked` が成功し、5コマンドの `--help` がPython 3.13環境で終了コード0を返す。

- [ ] 1.2 `src/app/config.py` と `src/app/paths.py` に `setting.ini`、`part_<model>.json`、安全な型番、座標、分割ID、比率、ブラックリスト、規定探索空間、スコア契約、拡張初期値、ORB最低マッチ数・RANSAC再投影誤差・RANSAC信頼確率・最低インライア比率のPydantic契約と既知ルート配下のパス解決を実装し、`config/setting.ini` と `config/part_XX.json` の初期テンプレートを追加する。`setting.ini` の初期テンプレートは `[IMAGE]` の `SIZE = 500` にインラインコメントを付けず、読込み時に値全体を正の整数へ変換する。対応: `REQ-001`、`REQ-002`、`REQ-003`、`REQ-005`、`REQ-006`、`REQ-007`、`REQ-010`、設計「データ契約と状態」「判断 2」「判断 5」「判断 6」「判断 10」、`TC-001`、`TC-002`、`TC-005`、`TC-008`、`TC-012`、`TC-014`、`TC-016`、`TC-022`、`TC-023`。完了条件: 有効な入力が型付き設定へ変換され、非整数・非正の `SIZE`、範囲外・ID重複・不正型番・未知ブラックリスト参照、`score.source`と`threshold.score_source`の不一致、PostProcessor有効化、および探索・拡張・位置合わせの範囲外値が書込み前に具体的な項目名付きで拒否される。

- [ ] 1.3 `src/app/runtime.py` と `src/app/cli.py` にCUDA優先・CPUフォールバック、依存版・OS・Python・デバイス情報、開始終了時刻、処理時間、警告・エラー、終了コードの共通実行記録を実装する。対応: `REQ-009`、設計「判断 8」「セキュリティ・性能・運用」、`TC-020`、`TC-021`。完了条件: GPU利用可否を差し替え可能な境界から選択結果と理由を取得でき、全CLIが同じ記録契約を使用する。

- [ ] 1.4 `src/app/contracts.py` に準備manifest、最良試行結果、分割検査結果、元画像検査結果、run metadataの列挙値・必須項目・UTC日時・JSON読書きを実装する。対応: `REQ-012`、設計「データ契約と状態」「判断 9」「判断 10」、`TC-027`。完了条件: normal/anomaly/undetermined/error、null score、checkpoint・`supersimplenet.pred_score`・PostProcessor状態・threshold・alignment・runtimeを検証してUTF-8 JSONへ往復でき、欠落・不正値を拒否する。

## 2. 画像準備フロー

- [ ] 2.1 `src/app/imaging.py`、`src/app/preparation.py`、`src/app/cli.py` の `check` 経路に、基準画像の読込み、`[x,x+SIZE) × [y,y+SIZE)` の範囲検証、矩形と分割IDの描画、ステージング後の確認画像置換を実装する。対応: `REQ-001`、設計「処理フロー 1-2」「インターフェースと失敗時の結果」「判断 2」、`TC-001`、`TC-002`。完了条件: 有効設定で `data/03_check/<model>.png` が生成され、無効設定では終了コード2となり既存確認画像が変更されない。

- [ ] 2.2 `src/app/imaging.py`、`src/app/preparation.py`、`src/app/cli.py` の `train-pre` 経路に、設定可能な最低マッチ数、RANSAC再投影誤差、RANSAC信頼確率、および返却マスクから算出する最低インライア比率によるORB位置合わせ、ブラックリスト除外、2桁分割IDの命名、学習manifest、警告付き位置合わせ失敗除外、範囲外時の原子的失敗を実装する。初期値は順に20、3.0px、0.995、0.5とする。対応: `REQ-002`、設計「処理フロー 2」「判断 7」、`TC-003`〜`TC-006`。完了条件: `data/04_train/<model>/` が成功時だけ一式で置換され、元画像を変更せず、対応点不足・ホモグラフィ推定失敗・インライア比率不足を区別してmanifest・ログから追跡できる。

- [ ] 2.3 `src/app/preparation.py` と `src/app/cli.py` の `test-pre` 経路に、学習準備と同じORB成功条件、ブラックリストを適用しない位置合わせ・分割、2桁分割IDの命名、位置合わせ失敗のundetermined引き継ぎ、範囲外時の原子的失敗を実装する。対応: `REQ-003`、設計「処理フロー 3」「判断 7」、`TC-007`〜`TC-009`。完了条件: `data/05_test/<model>/` の画像とmanifestが整合し、位置合わせ不能画像は正常入力扱いされず、対応点不足・ホモグラフィ推定失敗・インライア比率不足の理由付きで後続検査へ引き継がれる。

## 3. 学習・検査フロー

- [ ] 3.1 `src/app/training.py` に準備manifestの `source_image` をグループキーとするseed付きtrain/validation分離を実装し、同じ元画像の分割混在と空集合を禁止する。対応: `REQ-004`、設計「処理フロー 4」「判断 4」、`TC-010`、`TC-011`。完了条件: 80/20・seed 42で再現可能な非重複集合を返し、両集合を作れない場合は必要数と現在数を示して学習開始前に失敗する。

- [ ] 3.2 `src/app/modeling.py` と `src/app/training.py` に`post_processor=False`、`evaluator=False`、`visualizer=False`のAnomalib SuperSimpleNetアダプタとOptuna SQLite探索を実装する。adaptor/segmentation-detectionの既定学習率`0.0001`/`0.0002`へ共通倍率`0.25`〜`4.0`を対数適用し、batch `[4,8,16]`、epochs `[200,300,400]`、layers `[["layer2"],["layer2","layer3"],["layer3"]]`、前処理画像サイズ`[256,384,500]`を探索する。ImageNet正規化・bilinear・antialiasは固定し、seed 42のTPEとstartup 5試行・warmup 50 epoch・10 epoch間隔のMedianPrunerを使い、検証`pred_score`の99パーセンタイルを最小化する。対応: `REQ-005`、設計「判断 3」「判断 5」「判断 10」、`TC-012`、`TC-013`。完了条件: 枝刈り・失敗を含む合計50試行の条件・値・状態を保存し、正常完了試行の最小値を選び、CLIでは指標を「暫定探索指標」と表示して検出性能値や校正済み確率と称さない。

- [ ] 3.3 `src/app/modeling.py` に型番設定順で独立適用される平行移動±2%/確率0.5、回転±3度/0.5、明るさ・コントラスト係数0.9〜1.1/各0.3、6500K基準色温度±500K/0.2、ガンマ係数0.9〜1.1/0.3、平均0 Gaussianセンサーノイズ標準偏差0〜0.01/0.3、Gaussian blur kernel 3または5・sigma 0.1〜1.0/0.2の変換境界を実装する。幾何変換はreflection、色温度は1000K〜40000Kの黒体色近似による6500K比、画素値は0〜1制限、連続値は一様分布、seedは42とする。対応: `REQ-006`、設計「判断 6」、`TC-014`、`TC-015`。完了条件: 設定順・確率・範囲・seedが学習入力だけに適用され、検証・試験入力、元画像、準備画像に適用・永続化されない。

- [ ] 3.4 `src/app/modeling.py` と `src/app/training.py` に `wide_resnet50_2.tv_in1k` キャッシュ、型番別単一checkpoint、`best_trial.json`、最良モデルをeval・拡張なし・同一決定的前処理で学習集合へ再推論したPostProcessor適用前`pred_score`の99パーセンタイル暫定閾値、型番設定`threshold.value`の原子的同期を実装する。対応: `REQ-007`、設計「データ契約と状態」「判断 3」「判断 10」、`TC-016`、`TC-017`。完了条件: `weights/<model>.ckpt`、`optuna/<model>/best_trial.json`、型番設定が同じモデル、`supersimplenet.pred_score`・PostProcessor無効のスコア契約、閾値を参照し、既存pretrainedキャッシュが再取得されない。

- [ ] 3.5 `src/app/training.py`、`src/app/paths.py`、`src/app/cli.py` の `train` 経路に通常実行時の既存study再開と、`--restart` 時だけの `optuna/<model>/`・`weights/<model>.ckpt` 対象限定削除を実装する。対応: `REQ-008`、設計「インターフェースと失敗時の結果」「判断 7」、`TC-018`、`TC-019`。完了条件: 通常実行は完了試行を保持し、restartでも元画像・設定・pretrained・他型番成果物がバイト単位で保持される。

- [ ] 3.6 `src/app/modeling.py`、`src/app/evaluation.py`、`src/app/cli.py` の `test` 経路に、checkpoint・型番・`supersimplenet.pred_score`・PostProcessor無効・thresholdの整合性検証、閾値算出時と同じ決定的前処理、全分割への同一モデル推論、`pred_score >= threshold`判定、正常画像の未変更保存、PostProcessor適用前`anomaly_map`を分割画像サイズへリサイズした異常ヒートマップ保存を実装する。対応: `REQ-010`、設計「処理フロー 5」「判断 3」「判断 9」「判断 10」、`TC-022`、`TC-023`。完了条件: スコア契約不一致を推論前に拒否し、閾値未満・一致・超過の境界で期待する判定と結果画像が得られ、試験時にデータ拡張が呼ばれない。

- [ ] 3.7 `src/app/results.py` に `anomaly > undetermined/error > normal` の元画像集約を実装し、必要分割の不足、位置合わせ失敗、推論失敗を正常としない。対応: `REQ-011`、設計「処理フロー 6」「判断 9」、`TC-024`〜`TC-026`。完了条件: 異常を最優先し、必要分割が全てnormalの場合だけnormal、それ以外を再撮影案内付きundeterminedとして返す。

- [ ] 3.8 `src/app/results.py` と `src/app/evaluation.py` に分割スコア・判定・結果画像、元画像名、型番、checkpoint、スコア源、PostProcessor状態、threshold、処理日時、位置合わせ、警告・エラー、runtimeを含む元画像単位JSONの原子的保存を実装する。対応: `REQ-012`、設計「データ契約と状態」「処理フロー 6」「判断 10」、`TC-027`。完了条件: 正常・異常・未判定・エラーの各終了状態で必須契約を満たし、判定不能scoreがnullとなり、書込み失敗時は既存一式が維持される。

- [ ] 3.9 `src/app/evaluation.py`、`src/app/paths.py`、`src/app/cli.py` の `test --restart` 経路に、対象型番の `data/06_result/<model>/` だけを削除して現在の入力・model・thresholdから再生成する処理を実装する。対応: `REQ-013`、設計「インターフェースと失敗時の結果」「判断 7」、`TC-028`。完了条件: 旧結果だけが置換され、元画像・設定・pretrained・checkpoint・準備画像・他型番結果が保持される。

## 4. 自動試験

- [ ] 4.1 `tests/test_config.py` と `tests/test_preparation.py` に `TC-001`〜`TC-002` を実装し、コメントなしの正の整数 `SIZE` を使う有効な確認画像、座標境界、範囲外、ID重複、非整数・非正サイズ、不正型番を検証する。対応: `REQ-001`、設計「試験設計」。完了条件: design記載のpytest関数が存在し、`uv run --locked pytest tests/test_config.py tests/test_preparation.py -k 'check'` が成功する。

- [ ] 4.2 `tests/test_preparation.py` に固定画像と一時領域を用いた `TC-003`、`TC-004`、`TC-005`、`TC-006`、`TC-007`、`TC-008`、`TC-009` を実装し、学習・試験のORB最低マッチ数・RANSAC設定・返却マスク由来インライア比率、各失敗理由、命名、ブラックリスト差異、未判定引き継ぎ、範囲外時の原子性を検証する。対応: `REQ-002`、`REQ-003`、設計「試験設計」。完了条件: design記載の7つのpytest関数が存在し、対象テストがネットワーク・GPUなしで成功する。

- [ ] 4.3 `tests/test_training.py` にモデル・取得処理のテストダブルと一時SQLiteを用いた `TC-010`、`TC-011`、`TC-012`、`TC-013`、`TC-014`、`TC-015`、`TC-016`、`TC-017`、`TC-018`、`TC-019` を実装し、グループ分離、規定探索空間、TPE/MedianPruner、PostProcessor無効`pred_score`指標、拡張の順序・確率・範囲・seed、学習集合再推論による閾値、スコア契約、キャッシュ、再開、restart削除範囲を検証する。対応: `REQ-004`、`REQ-005`、`REQ-006`、`REQ-007`、`REQ-008`、設計「試験設計」。完了条件: design記載の10個のpytest関数が存在し、重い実学習を行わず決定的に成功する。

- [ ] 4.4 `tests/test_runtime.py`、`tests/test_evaluation.py`、`tests/test_results.py` に `TC-020`、`TC-021`、`TC-022`、`TC-023`、`TC-024`、`TC-025`、`TC-026`、`TC-027`、`TC-028` を実装し、GPU/CPU選択、スコア契約一致・不一致、PostProcessor無効`pred_score`の閾値境界、PostProcessor適用前`anomaly_map`ヒートマップ、集約優先順位、JSON契約、再検査削除範囲を検証する。対応: `REQ-009`、`REQ-010`、`REQ-011`、`REQ-012`、`REQ-013`、設計「試験設計」。完了条件: design記載の9個のpytest関数が存在し、GPUなしの開発環境でもテストダブルにより成功する。

- [ ] 4.5 `tests/test_platform_smoke.py` と `scripts/run_visual_inspection_smoke.py` に小規模フィクスチャで全CLI、成果物読戻し、実行記録、CPUフォールバックを検証する `TC-029`〜`TC-030` を実装する。対応: `NREQ-001`、設計「セキュリティ・性能・運用」「試験設計」。完了条件: design記載の2つのpytest関数が成功し、スモークスクリプトがOS・依存版・device・終了状態・durationをJSONへ保存する。

## 5. 品質・運用受け入れ

- [ ] 5.1 Ubuntu 24.04 LTS x86-64 と Windows 11 x86-64 の実機で、同じlockfileを使用して `scripts/run_visual_inspection_smoke.py` をGPU有効・GPU無効の両条件で実行し、採用NVIDIAドライバ版と結果を運用記録へ保存する。対応: `NREQ-001`、運用開始の受け入れ条件、設計「移行とロールバック」、`TC-029`、`TC-030`。完了条件: 両OSで学習・推論・結果保存・CPU切替が完了し、最低ドライバ要件以上の採用版を含む4経路の記録を評価者が確認できる。

- [ ] 5.2 `README.md` に設定配置、5コマンドの順序、通常再開と `--restart` の削除範囲、ORB成功条件、規定探索・拡張設定、PostProcessor無効`pred_score`と暫定閾値の関係、未判定時の再撮影、初期探索指標が本番性能値ではないこと、旧成果物の任意退避、ロールバック手順を記載する。対応: `REQ-002`、`REQ-005`、`REQ-006`、`REQ-007`、`REQ-008`、`REQ-010`、`REQ-011`、`REQ-013`、`NREQ-001`、設計「インターフェースと失敗時の結果」「判断 10」「移行とロールバック」。完了条件: 運用者が文書だけで初期評価フロー、設定値、スコア尺度、閾値算出、非対象範囲を判別でき、本番利用には別途数値基準と承認が必要と明記される。

- [ ] 5.3 全実装後に `uv run --locked pre-commit run --all-files`、`npm run check`、`uv run --locked python scripts/check_openspec_traceability.py --change visual-inspection`、`npx --no-install openspec validate visual-inspection --strict` を実行し、失敗を解消する。対応: 全要件、全 `TC-001`〜`TC-030`、設計「網羅性確認」。完了条件: 4コマンドがすべて終了コード0となり、未対応Scenario・TC・テスト実装先・秘密情報・未完了の品質エラーがない。
