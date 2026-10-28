# 受け入れ検証の証跡

## 自動検証

- 実施日: 2026-10-28
- 環境: Apple silicon macOS (arm64)、Python 3.13.15、pytest 9.1.1
- `uv run --locked pre-commit run --all-files`: 成功。Repository checks、Ruff lint、Ruff format が通過。
- `npm run check`: 成功。OpenSpec strict validation、Ruff、Pyright、pytest 469 件、repository checks、全 change の実装段階トレーサビリティが通過。
- `uv run --locked python scripts/check_openspec_traceability.py --change improve-check-visuals-and-alignment-options --phase implementation`: 成功。TC-001～TC-038 の参照テストを収集可能。
- `npx --no-install openspec validate improve-check-visuals-and-alignment-options --strict`: 成功。

自動試験では、分割枠・ラベルの描画、設定の検証、ORB・ECC・NONE の準備結果、ECC の既知変形と失敗、未判定への伝播、指紋不一致を確認した。

## 対象環境で残る確認

| 受け入れID | 状態 | 未完了タスク | 理由と確認内容 |
| --- | --- | --- | --- |
| AC-001 | 未検証 | 3.2 | Ubuntu 24.04 LTS と Apple silicon macOS の双方で、複数・重複分割の確認画像を表示して判読性を目視する。 |
| AC-002 | 未検証 | 3.3 | 双方の実CLIで方法選択、不正設定の拒否、旧成果物保持を確認する。 |
| AC-003 | 未検証 | 3.4 | 双方で ORB・ECC・NONE の準備・検査を実行し、manifest と結果を読み戻す。 |
| AC-004 | 未検証 | 3.5 | 運用実画像が未提供。双方で ECC の相関下限、推定変形量、分割位置、失敗例を確認する。 |
| AC-005 | 未検証 | 3.6 | 双方で方法・条件変更後の旧成果物拒否と全工程の再実行を確認する。 |

この作業環境には Ubuntu 24.04 LTS と運用実画像がない。<br />
Apple silicon macOS での自動試験の成功は、対象画像を使った実CLIの受け入れ確認を代替しない。

## 制限付きアーカイブの判断

2026-10-28、利用者は AC-001～AC-005 とタスク3.2～3.6を未検証のまま残す制限付きアーカイブ、および差分仕様の主仕様への同期を明示的に了承した。<br />
延期した条件は運用開始の承認を意味せず、対象OSと運用実画像での確認が完了するまで適用性は確定しない。
