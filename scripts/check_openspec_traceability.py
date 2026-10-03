"""Check requirement, test-design, and task traceability in OpenSpec changes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REQUIREMENT_PATTERN = re.compile(r"^### Requirement: ((?:N?REQ)-\d{3})\b", re.MULTILINE)
REQUIREMENT_ID_PATTERN = re.compile(r"\b(?:N?REQ)-\d{3}\b")
SCENARIO_PATTERN = re.compile(
    r"^#### Scenario: ((?:N?REQ)-\d{3}-S\d{2})\b", re.MULTILINE
)
PYTEST_REFERENCE_PATTERN = re.compile(r"^`?tests/.+\.py::test_[A-Za-z0-9_]+`?$")
TASK_LINE_PATTERN = re.compile(
    r"^\s*-\s*\[[^\]]*]\s+(?P<task_id>\d+\.\d+)\b(?P<description>.*)$"
)
TASK_REFERENCE_PATTERN = re.compile(r"(?<![\d.])\d+\.\d+(?![\d.])")


def markdown_table_rows(content: str, heading: str) -> list[list[str]]:
    """Extract data rows from the first Markdown table in a section."""
    if heading not in content:
        return []
    section = content.split(heading, maxsplit=1)[1]
    section = re.split(r"^## ", section, maxsplit=1, flags=re.MULTILINE)[0]
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if cells[0] in {"TC ID", "要件ID"}:
            continue
        rows.append(cells)
    return rows


def check_change(change_dir: Path) -> list[str]:
    """Return traceability errors for a single change directory."""
    errors: list[str] = []
    spec_files = sorted((change_dir / "specs").glob("**/spec.md"))
    design_file = change_dir / "design.md"
    tasks_file = change_dir / "tasks.md"
    if not spec_files or not design_file.is_file() or not tasks_file.is_file():
        return [
            f"{change_dir.name}: spec.md、design.md、tasks.md をすべて作成してください"
        ]

    requirements: set[str] = set()
    scenarios: set[str] = set()
    for spec_file in spec_files:
        content = spec_file.read_text(encoding="utf-8")
        found_requirements = set(REQUIREMENT_PATTERN.findall(content))
        requirements.update(found_requirements)
        found_scenarios = set(SCENARIO_PATTERN.findall(content))
        scenarios.update(found_scenarios)
        for requirement_id in found_requirements:
            if not any(
                scenario.startswith(f"{requirement_id}-")
                for scenario in found_scenarios
            ):
                errors.append(
                    f"{change_dir.name}: {requirement_id} に Scenario がありません"
                )

    design = design_file.read_text(encoding="utf-8")
    tasks = tasks_file.read_text(encoding="utf-8")
    task_lines = tasks.splitlines()
    task_requirements: dict[str, set[str]] = {}
    duplicate_task_ids: set[str] = set()
    for line in task_lines:
        task_match = TASK_LINE_PATTERN.match(line)
        if not task_match:
            continue
        task_id = task_match.group("task_id")
        if task_id in task_requirements:
            duplicate_task_ids.add(task_id)
            continue
        task_requirements[task_id] = set(
            REQUIREMENT_ID_PATTERN.findall(task_match.group("description"))
        )
    for task_id in sorted(duplicate_task_ids):
        errors.append(
            f"{change_dir.name}: tasks.md のタスク番号 {task_id} が重複しています"
        )

    traceability_requirements: set[str] = set()
    if "## 要件トレーサビリティ" not in design:
        errors.append(
            f"{change_dir.name}: design.md に要件トレーサビリティがありません"
        )
    else:
        traceability_rows = markdown_table_rows(design, "## 要件トレーサビリティ")
        for row in traceability_rows:
            if len(row) < 6 or not REQUIREMENT_ID_PATTERN.fullmatch(row[0]):
                errors.append(f"{change_dir.name}: 要件トレーサビリティの行が不正です")
                continue
            requirement_id = row[0]
            traceability_requirements.add(requirement_id)
            if requirement_id not in requirements:
                continue
            referenced_tasks = TASK_REFERENCE_PATTERN.findall(row[3])
            if not referenced_tasks:
                errors.append(
                    f"{change_dir.name}: {requirement_id} に実装タスク参照がありません"
                )
                continue
            for task_id in referenced_tasks:
                if task_id not in task_requirements:
                    errors.append(
                        f"{change_dir.name}: {requirement_id} が参照する実装タスク "
                        f"{task_id} は tasks.md に存在しません"
                    )
                elif requirement_id not in task_requirements[task_id]:
                    errors.append(
                        f"{change_dir.name}: {requirement_id} が参照する実装タスク "
                        f"{task_id} はその要件を扱っていません"
                    )

    for requirement_id in sorted(requirements - traceability_requirements):
        errors.append(
            f"{change_dir.name}: 要件トレーサビリティに {requirement_id} がありません"
        )
    for requirement_id in sorted(traceability_requirements - requirements):
        errors.append(
            f"{change_dir.name}: 要件トレーサビリティの {requirement_id} "
            "は仕様に存在しません"
        )

    if "## 試験設計" not in design:
        return [*errors, f"{change_dir.name}: design.md に試験設計がありません"]
    test_cases = markdown_table_rows(design, "## 試験設計")
    scenario_cases: dict[str, list[tuple[str, str]]] = {}
    for row in test_cases:
        if len(row) < 8 or not row[0].startswith("TC-"):
            errors.append(f"{change_dir.name}: 試験設計の試験ケース行が不正です")
            continue
        tc_id, _requirement_id, scenario_id, *_details, pytest_reference, _automated = (
            row
        )
        scenario_cases.setdefault(scenario_id, []).append((tc_id, pytest_reference))

    for scenario_id in scenarios:
        cases = scenario_cases.get(scenario_id, [])
        if not cases:
            errors.append(f"{change_dir.name}: {scenario_id} に TC-ID がありません")
            continue
        for tc_id, pytest_reference in cases:
            if not PYTEST_REFERENCE_PATTERN.fullmatch(pytest_reference):
                errors.append(
                    f"{change_dir.name}: {tc_id} の pytest 実装先が不正です: {pytest_reference}"
                )

    for cases in scenario_cases.values():
        for tc_id, _pytest_reference in cases:
            has_test_task = any(
                line.lstrip().startswith("- [")
                and tc_id in line
                and "pytest" in line
                and "tests/" in line
                for line in task_lines
            )
            if not has_test_task:
                errors.append(
                    f"{change_dir.name}: {tc_id} に対応する pytest テスト作成・実行タスクがありません"
                )
    return errors


def parse_arguments() -> argparse.Namespace:
    """Parse the change selection arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--change", help="openspec/changes 配下の change 名")
    selection.add_argument(
        "--all", action="store_true", help="すべての進行中 change を検査する"
    )
    return parser.parse_args()


def main() -> int:
    """Run selected traceability checks from the repository root."""
    arguments = parse_arguments()
    changes_root = Path.cwd() / "openspec" / "changes"
    if arguments.change:
        change_dirs = [changes_root / arguments.change]
    elif not changes_root.is_dir():
        change_dirs = []
    else:
        change_dirs = [
            path
            for path in changes_root.iterdir()
            if path.is_dir() and path.name != "archive"
        ]
    errors = [error for change_dir in change_dirs for error in check_change(change_dir)]
    if errors:
        print(
            "OpenSpec traceability checks failed:", *errors, sep="\n", file=sys.stderr
        )
        return 1
    print("OpenSpec traceability checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
