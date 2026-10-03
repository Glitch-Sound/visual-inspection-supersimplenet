from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/check_openspec_traceability.py")


def write_change(root: Path, *, include_scenario: bool = True) -> None:
    """Create a minimal change that follows the project traceability format."""
    change = root / "openspec" / "changes" / "example"
    spec_dir = change / "specs" / "example"
    spec_dir.mkdir(parents=True)
    req_scenario = (
        """
#### Scenario: REQ-001-S01 正常系

- **WHEN** 実行する
- **THEN** 結果を返す
"""
        if include_scenario
        else ""
    )
    (spec_dir / "spec.md").write_text(
        f"""## ADDED Requirements

### Requirement: REQ-001 例

システムは、結果を返さなければならない。
{req_scenario}

### Requirement: NREQ-001 性能

システムは、処理時に定められた時間内で結果を返さなければならない。

#### Scenario: NREQ-001-S01 性能検証

- **WHEN** 処理を実行する
- **THEN** 定められた時間内に結果を返す
""",
        encoding="utf-8",
    )
    (change / "design.md").write_text(
        """## 要件トレーサビリティ

| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | 業務フロー | 結果生成 | 2.1 | TC-001 | 単体試験 |
| NREQ-001 | 性能 | 処理時間 | 2.2 | TC-002 | 性能試験 |

## 試験設計

| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TC-001 | REQ-001 | REQ-001-S01 | unit | 実行する | 結果 | `tests/test_example.py::test_requirement` | はい |
| TC-002 | NREQ-001 | NREQ-001-S01 | performance | 実行する | 時間内に結果 | `tests/test_example.py::test_performance` | はい |
""",
        encoding="utf-8",
    )
    (change / "tasks.md").write_text(
        "- [ ] 2.1 結果生成を実装する。対応: REQ-001。\n"
        "- [ ] 2.2 処理時間を検証可能にする。対応: NREQ-001。\n"
        "- [ ] 3.1 `tests/test_example.py` に TC-001 の pytest テストを追加する。"
        " 対応: REQ-001 / REQ-001-S01。\n"
        "- [ ] 3.2 `tests/test_example.py` に TC-002 の pytest テストを追加する。"
        " 対応: NREQ-001 / NREQ-001-S01。\n",
        encoding="utf-8",
    )


def run_check(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the script from a temporary repository root."""
    return subprocess.run(  # noqa: S603 -- test controls the fixed interpreter and script path.
        [sys.executable, str(SCRIPT_PATH.resolve()), *arguments],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )


def test_check_passes_when_requirements_and_tasks_are_unique_and_traced(
    tmp_path: Path,
) -> None:
    write_change(tmp_path)

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 0
    assert "passed" in result.stdout


def test_check_reports_duplicate_task_id(tmp_path: Path) -> None:
    write_change(tmp_path)
    tasks_file = tmp_path / "openspec" / "changes" / "example" / "tasks.md"
    tasks_file.write_text(
        tasks_file.read_text(encoding="utf-8")
        + "- [ ] 2.1 重複した処理を実装する。対応: REQ-001。\n",
        encoding="utf-8",
    )

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert "example: tasks.md のタスク番号 2.1 が重複しています" in result.stderr


def test_check_reports_requirement_missing_from_traceability(tmp_path: Path) -> None:
    write_change(tmp_path)
    design_file = tmp_path / "openspec" / "changes" / "example" / "design.md"
    design_file.write_text(
        design_file.read_text(encoding="utf-8").replace(
            "| REQ-001 | 業務フロー | 結果生成 | 2.1 | TC-001 | 単体試験 |\n",
            "",
        ),
        encoding="utf-8",
    )

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert "example: 要件トレーサビリティに REQ-001 がありません" in result.stderr


def test_check_reports_non_functional_requirement_missing_from_traceability(
    tmp_path: Path,
) -> None:
    write_change(tmp_path)
    design_file = tmp_path / "openspec" / "changes" / "example" / "design.md"
    design_file.write_text(
        design_file.read_text(encoding="utf-8").replace(
            "| NREQ-001 | 性能 | 処理時間 | 2.2 | TC-002 | 性能試験 |\n",
            "",
        ),
        encoding="utf-8",
    )

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert "example: 要件トレーサビリティに NREQ-001 がありません" in result.stderr


def test_check_reports_unknown_requirement_in_traceability(tmp_path: Path) -> None:
    write_change(tmp_path)
    design_file = tmp_path / "openspec" / "changes" / "example" / "design.md"
    design_file.write_text(
        design_file.read_text(encoding="utf-8").replace(
            "## 試験設計",
            "| REQ-999 | 業務フロー | 未知の責務 | 2.1 | TC-999 | 単体試験 |\n\n"
            "## 試験設計",
        ),
        encoding="utf-8",
    )

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert (
        "example: 要件トレーサビリティの REQ-999 は仕様に存在しません" in result.stderr
    )


def test_check_all_passes_when_changes_directory_does_not_exist(tmp_path: Path) -> None:
    result = run_check(tmp_path, "--all")

    assert result.returncode == 0
    assert "passed" in result.stdout


def test_check_reports_requirement_without_scenario(tmp_path: Path) -> None:
    write_change(tmp_path, include_scenario=False)

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert "REQ-001 に Scenario がありません" in result.stderr


def test_check_reports_missing_test_task(tmp_path: Path) -> None:
    write_change(tmp_path)
    tasks_file = tmp_path / "openspec" / "changes" / "example" / "tasks.md"
    tasks_file.write_text(
        "- [ ] 2.1 結果生成を実装する。対応: REQ-001。\n"
        "- [ ] 2.2 処理時間を検証可能にする。対応: NREQ-001。\n",
        encoding="utf-8",
    )

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert (
        "TC-001 に対応する pytest テスト作成・実行タスクがありません" in result.stderr
    )


def test_check_reports_missing_task_referenced_by_design(tmp_path: Path) -> None:
    write_change(tmp_path)
    design_file = tmp_path / "openspec" / "changes" / "example" / "design.md"
    design_file.write_text(
        design_file.read_text(encoding="utf-8").replace(
            "| REQ-001 | 業務フロー | 結果生成 | 2.1 |",
            "| REQ-001 | 業務フロー | 結果生成 | 9.9 |",
        ),
        encoding="utf-8",
    )

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert (
        "REQ-001 が参照する実装タスク 9.9 は tasks.md に存在しません" in result.stderr
    )


def test_check_reports_task_for_different_requirement(tmp_path: Path) -> None:
    write_change(tmp_path)
    tasks_file = tmp_path / "openspec" / "changes" / "example" / "tasks.md"
    tasks_file.write_text(
        tasks_file.read_text(encoding="utf-8").replace(
            "2.1 結果生成を実装する。対応: REQ-001。",
            "2.1 位置合わせを実装する。対応: REQ-002。",
        ),
        encoding="utf-8",
    )

    result = run_check(tmp_path, "--change", "example")

    assert result.returncode == 1
    assert (
        "REQ-001 が参照する実装タスク 2.1 はその要件を扱っていません" in result.stderr
    )
