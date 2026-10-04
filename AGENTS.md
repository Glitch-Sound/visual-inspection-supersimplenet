# 開発エージェント向け共通指示

このリポジトリは Python / OpenSpec 開発テンプレートである。作業前に `README.md`、`openspec/product.md`、`openspec/tech.md`、`openspec/structure.md` を確認する。

## 作業の選択

- 誤字、雛形・開発基盤の保守、既存仕様の振る舞いを変えないリファクタリング、テストのみの修正は、OpenSpec change を作らず直接変更してよい。
- 利用者・外部システムから観測できる振る舞い、公開 API、永続データ、権限・セキュリティ、性能目標、外部連携、移行・運用手順を変える場合は、実装前に OpenSpec change を作成し、その成果物に従う。
- 判断に迷う場合は、要件を捏造せず利用者に確認する。変更と無関係なリファクタリングや依存関係更新を混在させない。

## 完了条件

- 直接変更では、影響に応じて `pre-commit run --all-files` または `npm run check` を実行する。
- OpenSpec change では、実装前に成果物と設計段階の対応を確認する。実装後は `--phase implementation` で参照テストの収集可否も確認し、verify / archive 前には `uv run --locked python scripts/check_openspec_traceability.py --change <change-name> --phase complete` と `npx --no-install openspec validate <change-name> --strict` を実行する。
- 自動試験の成功と実機・対象OSでの受け入れ確認を区別する。proposal の受け入れ条件に `AC-001` 形式のIDを付け、design の「受け入れ検証」に検証範囲・条件、方法、残る検証、状態、証跡を対応付ける。証跡の内容と対象環境をレビューし、未完了タスク・未検証条件が残る場合はアーカイブしない。仕様反映だけが必要なら sync を使い、change は進行中に残す。
- 秘密情報をコード、仕様、ログ、テストデータに含めない。
