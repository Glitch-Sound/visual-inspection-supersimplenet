from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

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


def replace_design(root: Path, old: str, new: str) -> None:
    path = root / "openspec/changes/example/design.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )


def write_tests(root: Path) -> Path:
    path = root / "tests/test_example.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "def test_requirement():\n    assert True\n\n"
        "def test_performance():\n    assert True\n",
        encoding="utf-8",
    )
    return path


def write_complete_change(root: Path) -> None:
    write_change(root)
    write_tests(root)
    change = root / "openspec/changes/example"
    tasks = change / "tasks.md"
    tasks.write_text(
        tasks.read_text(encoding="utf-8").replace("[ ]", "[x]"), encoding="utf-8"
    )
    (change / "proposal.md").write_text(
        "## 運用開始の受け入れ条件\n\n- AC-001: 結果を検証できる。\n",
        encoding="utf-8",
    )
    design = change / "design.md"
    design.write_text(
        design.read_text(encoding="utf-8") + "\n## 受け入れ検証\n\n"
        "| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| AC-001 | CLI正常・異常系 | pytest実行 | なし | 検証済み | `report.md` |\n",
        encoding="utf-8",
    )
    (root / "report.md").write_text("検証結果: 成功\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            "| TC-001 | REQ-001 |",
            "| TC-001 | REQ-999 |",
            "要件 REQ-999 は仕様に存在しません",
        ),
        ("| TC-001 | REQ-001 |", "| TC-001 | NREQ-001 |", "所属要件が一致しません"),
        (
            "| REQ-001-S01 | unit |",
            "| REQ-999-S01 | unit |",
            "Scenario REQ-999-S01 は仕様に存在しません",
        ),
    ],
)
def test_check_rejects_invalid_test_case_mapping(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    write_change(tmp_path)
    replace_design(tmp_path, old, new)
    result = run_check(tmp_path, "--change", "example")
    assert result.returncode == 1
    assert message in result.stderr


@pytest.mark.parametrize("duplicate", ["requirement", "scenario", "case"])
def test_check_rejects_duplicate_spec_and_case_ids(
    tmp_path: Path, duplicate: str
) -> None:
    write_change(tmp_path)
    change = tmp_path / "openspec/changes/example"
    if duplicate == "case":
        path = change / "design.md"
        line = next(
            line
            for line in path.read_text().splitlines()
            if line.startswith("| TC-001 |")
        )
    else:
        path = change / "specs/example/spec.md"
        line = (
            "### Requirement: REQ-001 重複\n\n#### Scenario: REQ-001-S02 重複要件のシナリオ\n"
            if duplicate == "requirement"
            else "#### Scenario: NREQ-001-S01 重複\n"
        )
    path.write_text(
        path.read_text(encoding="utf-8") + "\n" + line + "\n", encoding="utf-8"
    )
    result = run_check(tmp_path, "--change", "example")
    assert result.returncode == 1
    assert "重複しています" in result.stderr


@pytest.mark.parametrize(
    "kind", ["function", "parameterized", "class", "extended-table"]
)
def test_implementation_collects_referenced_tests(tmp_path: Path, kind: str) -> None:
    write_change(tmp_path)
    test_file = write_tests(tmp_path)
    if kind == "parameterized":
        test_file.write_text(
            "import pytest\n\n@pytest.mark.parametrize('value', [1, 2])\n"
            "def test_requirement(value):\n    assert value > 0\n\n"
            "def test_performance():\n    assert True\n",
            encoding="utf-8",
        )
    elif kind == "class":
        test_file.write_text(
            "class TestExample:\n    def test_requirement(self):\n        assert True\n\n"
            "def test_performance():\n    assert True\n",
            encoding="utf-8",
        )
        replace_design(
            tmp_path, "py::test_requirement", "py::TestExample::test_requirement"
        )
    elif kind == "extended-table":
        replace_design(
            tmp_path, "| はい |", "| はい | CLI契約のみ | 実機スモーク | report.md |"
        )
    result = run_check(tmp_path, "--change", "example", "--phase", "implementation")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("missing", ["file", "function", "not-collected"])
def test_implementation_rejects_missing_test_reference(
    tmp_path: Path, missing: str
) -> None:
    write_change(tmp_path)
    if missing != "file":
        test_file = write_tests(tmp_path)
        if missing == "function":
            replace_design(tmp_path, "py::test_requirement", "py::test_missing")
        else:
            test_file.write_text(
                "def test_requirement():\n    assert True\n"
                "test_requirement.__test__ = False\n\n"
                "def test_performance():\n    assert True\n",
                encoding="utf-8",
            )
    result = run_check(tmp_path, "--change", "example", "--phase", "implementation")
    assert result.returncode == 1
    assert "存在しません" in result.stderr or "収集されません" in result.stderr


def test_implementation_reports_collection_failure(tmp_path: Path) -> None:
    write_change(tmp_path)
    test_file = write_tests(tmp_path)
    test_file.write_text("raise RuntimeError('collection failed')\n", encoding="utf-8")
    result = run_check(tmp_path, "--change", "example", "--phase", "implementation")
    assert result.returncode == 1
    assert "pytest 収集に失敗しました" in result.stderr
    assert "collection failed" in result.stderr


@pytest.mark.parametrize("marker", [" ", "", "-", "~", "?", "!"])
def test_complete_rejects_unfinished_tasks(tmp_path: Path, marker: str) -> None:
    write_complete_change(tmp_path)
    tasks = tmp_path / "openspec/changes/example/tasks.md"
    tasks.write_text(
        tasks.read_text().replace("[x] 2.1", f"[{marker}] 2.1"), encoding="utf-8"
    )
    result = run_check(tmp_path, "--change", "example", "--phase", "complete")
    assert result.returncode == 1
    assert "未完了タスク: 2.1" in result.stderr


@pytest.mark.parametrize(
    "fault",
    [
        "missing-record",
        "unknown-id",
        "duplicate-record",
        "duplicate-condition",
        "unverified",
        "remaining",
        "missing-evidence",
        "empty-evidence",
        "outside-evidence",
        "symlink-evidence",
        "missing-id",
        "unidentified-condition",
        "blank-method",
        "missing-proposal",
    ],
)
def test_complete_rejects_invalid_acceptance_evidence(
    tmp_path: Path, fault: str
) -> None:
    write_complete_change(tmp_path)
    change = tmp_path / "openspec/changes/example"
    design = change / "design.md"
    proposal = change / "proposal.md"
    text = design.read_text()
    record = "| AC-001 | CLI正常・異常系 | pytest実行 | なし | 検証済み | `report.md` |"
    if fault == "missing-record":
        text = text.replace(record, "")
    elif fault == "unknown-id":
        text = text.replace("| AC-001 |", "| AC-999 |")
    elif fault == "duplicate-record":
        text += record + "\n"
    elif fault == "duplicate-condition":
        proposal.write_text(
            proposal.read_text() + "- AC-001: 重複条件\n", encoding="utf-8"
        )
    elif fault == "unverified":
        text = text.replace("検証済み", "未検証")
    elif fault == "remaining":
        text = text.replace("| なし |", "| Windows実機試験 |")
    elif fault == "missing-evidence":
        text = text.replace("`report.md`", "`missing.md`")
    elif fault == "empty-evidence":
        (tmp_path / "report.md").write_text(" \n", encoding="utf-8")
    elif fault in {"outside-evidence", "symlink-evidence"}:
        outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
        outside.write_text("外部証跡\n", encoding="utf-8")
        if fault == "symlink-evidence":
            (tmp_path / "linked.md").symlink_to(outside)
            text = text.replace("`report.md`", "`linked.md`")
        else:
            text = text.replace("`report.md`", f"`{outside}`")
    elif fault == "missing-id":
        proposal.write_text(
            proposal.read_text().replace("AC-001: ", ""), encoding="utf-8"
        )
    elif fault == "unidentified-condition":
        proposal.write_text(
            proposal.read_text() + "* 実機確認も必要。\n", encoding="utf-8"
        )
    elif fault == "blank-method":
        text = text.replace("| pytest実行 |", "|  |")
    elif fault == "missing-proposal":
        proposal.rename(change / "unused.md")
    design.write_text(text, encoding="utf-8")
    result = run_check(tmp_path, "--change", "example", "--phase", "complete")
    assert result.returncode == 1
    assert any(word in result.stderr for word in ("受け入れ", "AC-001", "proposal.md"))


def test_complete_accepts_verified_change(tmp_path: Path) -> None:
    write_complete_change(tmp_path)
    tasks = tmp_path / "openspec/changes/example/tasks.md"
    tasks.write_text(tasks.read_text().replace("[x]", "[ X ]"), encoding="utf-8")
    result = run_check(tmp_path, "--change", "example", "--phase", "complete")
    assert result.returncode == 0, result.stderr


def write_limited_change(root: Path) -> Path:
    write_complete_change(root)
    change = root / "openspec/changes/example"
    tasks = change / "tasks.md"
    tasks.write_text(
        tasks.read_text(encoding="utf-8")
        + "\n- [ ] 3.3 AC-001 を対象OSの実機で検証する。\n",
        encoding="utf-8",
    )
    design = change / "design.md"
    design.write_text(
        design.read_text(encoding="utf-8").replace(
            "| なし | 検証済み | `report.md` |",
            "| 対象OSの実機試験 | 未検証 | 未作成 |",
        ),
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "## 延期中の受け入れ確認\n\n"
        "| change | 受け入れID | 状態 | 記録 |\n"
        "| --- | --- | --- | --- |\n"
        "| example | AC-001 | 未検証 | タスク3.3: 対象OSの実機確認 |\n",
        encoding="utf-8",
    )
    return change


def test_limited_archive_accepts_deferred_acceptance(tmp_path: Path) -> None:
    write_limited_change(tmp_path)
    result = run_check(tmp_path, "--change", "example", "--phase", "limited-archive")
    assert result.returncode == 0, result.stderr
    strict = run_check(tmp_path, "--change", "example", "--phase", "complete")
    assert strict.returncode == 1


def test_limited_archive_accepts_archived_change(tmp_path: Path) -> None:
    change = write_limited_change(tmp_path)
    archive = change.parent / "archive"
    archive.mkdir()
    change.rename(archive / "2026-10-05-example")
    result = run_check(
        tmp_path,
        "--change",
        "archive/2026-10-05-example",
        "--phase",
        "limited-archive",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "fault",
    [
        "missing-record",
        "extra-task",
        "wrong-ac",
        "checked-task",
        "missing-readme",
        "wrong-task",
        "wrong-state",
    ],
)
def test_limited_archive_rejects_invalid_handoff(tmp_path: Path, fault: str) -> None:
    change = write_limited_change(tmp_path)
    record = tmp_path / "README.md"
    tasks = change / "tasks.md"
    if fault == "missing-record":
        record.write_text("## 延期中の受け入れ確認\n", encoding="utf-8")
    elif fault == "missing-readme":
        record.unlink()
    elif fault == "extra-task":
        tasks.write_text(tasks.read_text() + "- [ ] 4.1 実装を終える。\n")
    elif fault == "wrong-ac":
        record.write_text(
            record.read_text().replace("AC-001 | 未検証", "AC-999 | 未検証")
        )
    elif fault == "wrong-task":
        record.write_text(record.read_text().replace("タスク3.3", "タスク9.9"))
    elif fault == "wrong-state":
        record.write_text(record.read_text().replace("未検証", "検証済み"))
    else:
        tasks.write_text(tasks.read_text().replace("[ ] 3.3", "[x] 3.3"))
    result = run_check(tmp_path, "--change", "example", "--phase", "limited-archive")
    assert result.returncode == 1


@pytest.mark.parametrize("selection", ["individual", "all"])
def test_check_includes_archived_changes_when_requested(
    tmp_path: Path, selection: str
) -> None:
    write_complete_change(tmp_path)
    change = tmp_path / "openspec/changes/example"
    tasks = change / "tasks.md"
    tasks.write_text(tasks.read_text().replace("[x] 2.1", "[ ] 2.1"), encoding="utf-8")
    archive = change.parent / "archive"
    archive.mkdir()
    change.rename(archive / "2026-10-03-example")
    args = (
        ["--all", "--include-archived"]
        if selection == "all"
        else ["--change", "archive/2026-10-03-example"]
    )
    result = run_check(tmp_path, *args, "--phase", "complete")
    assert result.returncode == 1
    assert "2026-10-03-example: 未完了タスク: 2.1" in result.stderr


def test_check_all_excludes_archived_changes(tmp_path: Path) -> None:
    write_change(tmp_path)
    change = tmp_path / "openspec/changes/example"
    archive = change.parent / "archive"
    archive.mkdir()
    change.rename(archive / "2026-10-03-example")
    result = run_check(tmp_path, "--all", "--phase", "complete")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("selection", ["../outside", "absolute", "symlink"])
def test_check_rejects_change_outside_root(tmp_path: Path, selection: str) -> None:
    write_change(tmp_path)
    if selection == "absolute":
        selection = str(tmp_path.resolve())
    elif selection == "symlink":
        (tmp_path / "openspec/changes/linked").symlink_to(tmp_path)
        selection = "linked"
    result = run_check(tmp_path, "--change", selection)
    assert result.returncode == 1
    assert "openspec/changes 配下ではありません" in result.stderr


def test_check_does_not_match_partial_test_case_id(tmp_path: Path) -> None:
    write_change(tmp_path)
    tasks = tmp_path / "openspec/changes/example/tasks.md"
    tasks.write_text(tasks.read_text().replace("TC-001", "TC-0010"), encoding="utf-8")
    result = run_check(tmp_path, "--change", "example")
    assert result.returncode == 1
    assert "TC-001 に対応する pytest" in result.stderr


def test_skip_specs_change_checks_design_tasks_and_acceptance(tmp_path: Path) -> None:
    change = tmp_path / "openspec/changes/example"
    change.mkdir(parents=True)
    (change / ".openspec.yaml").write_text("skip_specs: true\n", encoding="utf-8")
    (change / "proposal.md").write_text(
        "## 運用開始の受け入れ条件\n\n- AC-001: 既存の結果を維持する。\n",
        encoding="utf-8",
    )
    design = change / "design.md"
    original_design = (
        "## 要件トレーサビリティ\n\n"
        "| 要件ID | 対応する設計節 | 責務・境界 | 実装タスク | 試験ケース | 検証方法 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| AC-001 | 責務 | 結果 | 1.1 | TC-001 | pytest |\n\n"
        "## 試験設計\n\n"
        "| TC ID | 要件ID | Scenario ID | テスト層 | 前提・操作 | 期待値 | pytest 実装 | 自動化 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        "| TC-001 | AC-001 | 該当なし | unit | 実行 | 同じ結果 | `tests/test_example.py::test_result` | はい |\n\n"
        "## 受け入れ検証\n\n"
        "| 受け入れID | 検証範囲・条件 | 検証方法 | 残る検証 | 状態 | 証跡 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| AC-001 | CLI契約 | pytest | なし | 検証済み | `report.md` |\n"
    )
    design.write_text(original_design, encoding="utf-8")
    tasks = change / "tasks.md"
    tasks.write_text(
        "- [ ] 1.1 `tests/test_example.py` に pytest を実装する。"
        "対応: AC-001、TC-001。\n",
        encoding="utf-8",
    )

    assert run_check(tmp_path, "--change", "example").returncode == 0
    for old, new, expected in (
        ("| AC-001 | 責務", "| AC-999 | 責務", "proposal に存在しません"),
        ("| 1.1 | TC-001 |", "| 9.9 | TC-001 |", "tasks.md に存在しません"),
        ("| TC-001 | AC-001 |", "| TC-001 | AC-999 |", "proposal に存在しません"),
        (
            "| TC-001 | AC-001 | 該当なし |",
            "| TC-001 | AC-001 | REQ-001-S01 |",
            "Scenario",
        ),
        ("test_result`", "missing`", "pytest 実装先が不正"),
    ):
        design.write_text(original_design.replace(old, new), encoding="utf-8")
        result = run_check(tmp_path, "--change", "example")
        assert result.returncode == 1
        assert expected in result.stderr
    design.write_text(original_design, encoding="utf-8")
    tasks.write_text(tasks.read_text().replace("TC-001", "TC-999"), encoding="utf-8")
    assert (
        "TC-001 に対応する pytest" in run_check(tmp_path, "--change", "example").stderr
    )
    tasks.write_text(tasks.read_text().replace("TC-999", "TC-001"), encoding="utf-8")

    collection = run_check(tmp_path, "--change", "example", "--phase", "implementation")
    assert collection.returncode == 1
    assert "pytest 実装ファイルが存在しません" in collection.stderr
    test_file = tmp_path / "tests/test_example.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_result():\n    assert True\n", encoding="utf-8")
    assert (
        run_check(
            tmp_path, "--change", "example", "--phase", "implementation"
        ).returncode
        == 0
    )

    incomplete = run_check(tmp_path, "--change", "example", "--phase", "complete")
    assert incomplete.returncode == 1
    assert "未完了タスク" in incomplete.stderr
    assert "証跡が存在しない" in incomplete.stderr
    tasks.write_text(tasks.read_text().replace("[ ]", "[x]"), encoding="utf-8")
    (tmp_path / "report.md").write_text("試験成功\n", encoding="utf-8")
    assert (
        run_check(tmp_path, "--change", "example", "--phase", "complete").returncode
        == 0
    )

    tasks.write_text(
        tasks.read_text(encoding="utf-8")
        + "\n- [ ] 2.1 AC-001 を対象OSの実機で検証する。\n",
        encoding="utf-8",
    )
    design.write_text(
        original_design.replace(
            "| なし | 検証済み | `report.md` |",
            "| 対象OSの実機試験 | 未検証 | 未作成 |",
        ),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "## 延期中の受け入れ確認\n\n"
        "| change | 受け入れID | 状態 | 記録 |\n"
        "| --- | --- | --- | --- |\n"
        "| example | AC-001 | 未検証 | タスク2.1: 対象OSの実機確認 |\n",
        encoding="utf-8",
    )
    limited = run_check(tmp_path, "--change", "example", "--phase", "limited-archive")
    assert limited.returncode == 0, limited.stderr
    assert (
        run_check(tmp_path, "--change", "example", "--phase", "complete").returncode
        == 1
    )

    normal = tmp_path / "openspec/changes/normal"
    normal.mkdir()
    (normal / "design.md").write_text(original_design, encoding="utf-8")
    (normal / "tasks.md").write_text(tasks.read_text(), encoding="utf-8")
    conventional = run_check(tmp_path, "--change", "normal")
    assert conventional.returncode == 1
    assert "spec.md、design.md、tasks.md" in conventional.stderr
