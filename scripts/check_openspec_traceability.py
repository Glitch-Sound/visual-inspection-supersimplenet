"""Check requirement, test-design, and task traceability in OpenSpec changes."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REQUIREMENT_PATTERN = re.compile(r"^### Requirement: ((?:N?REQ)-\d{3})\b", re.MULTILINE)
REQUIREMENT_ID_PATTERN = re.compile(r"\b(?:N?REQ)-\d{3}\b")
SCENARIO_PATTERN = re.compile(
    r"^#### Scenario: ((?:N?REQ)-\d{3}-S\d{2})\b", re.MULTILINE
)
PYTEST_REFERENCE_PATTERN = re.compile(
    r"^tests/[^\s`]+\.py::(?:Test[A-Za-z0-9_]+::)*test_[A-Za-z0-9_]+$"
)
TEST_CASE_ID_PATTERN = re.compile(r"\bTC-\d{3}\b")
ACCEPTANCE_ID_PATTERN = re.compile(r"^AC-\d{3}$")
TASK_LINE_PATTERN = re.compile(
    r"^\s*-\s*\[(?P<status>[^\]]*)]\s+(?P<task_id>\d+\.\d+)\b(?P<description>.*)$"
)
TASK_REFERENCE_PATTERN = re.compile(r"(?<![\d.])\d+\.\d+(?![\d.])")


def markdown_section(content: str, heading: str) -> str:
    """Return a level-two section, excluding HTML comments."""
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    match = re.search(rf"^{re.escape(heading)}\s*$", content, re.MULTILINE)
    if match is None:
        return ""
    return re.split(r"^## ", content[match.end() :], maxsplit=1, flags=re.MULTILINE)[0]


def markdown_table_rows(content: str, heading: str) -> list[list[str]]:
    """Extract data rows from the first Markdown table in a section."""
    section = markdown_section(content, heading)
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if cells[0] in {"TC ID", "要件ID", "受け入れID"}:
            continue
        rows.append(cells)
    return rows


def check_change(
    change_dir: Path, *, phase: str = "design", repository_root: Path | None = None
) -> list[str]:
    """Return traceability errors for a single change directory."""
    errors: list[str] = []
    repository_root = (repository_root or Path.cwd()).resolve()
    spec_files = sorted((change_dir / "specs").glob("**/spec.md"))
    design_file = change_dir / "design.md"
    tasks_file = change_dir / "tasks.md"
    if not spec_files or not design_file.is_file() or not tasks_file.is_file():
        return [
            f"{change_dir.name}: spec.md、design.md、tasks.md をすべて作成してください"
        ]

    requirements: set[str] = set()
    scenarios: set[str] = set()
    scenario_requirements: dict[str, str] = {}
    for spec_file in spec_files:
        content = re.sub(
            r"<!--.*?-->", "", spec_file.read_text(encoding="utf-8"), flags=re.DOTALL
        )
        for requirement_id in REQUIREMENT_PATTERN.findall(content):
            if requirement_id in requirements:
                errors.append(
                    f"{change_dir.name}: 要件ID {requirement_id} が重複しています"
                )
            requirements.add(requirement_id)
        owner: str | None = None
        for line in content.splitlines():
            requirement_match = REQUIREMENT_PATTERN.match(line)
            if requirement_match:
                owner = requirement_match[1]
            elif line.startswith(("## ", "### ")):
                owner = None
            scenario_match = SCENARIO_PATTERN.match(line)
            if not scenario_match:
                continue
            scenario_id = scenario_match[1]
            if scenario_id in scenarios:
                errors.append(
                    f"{change_dir.name}: Scenario ID {scenario_id} が重複しています"
                )
            scenarios.add(scenario_id)
            if owner is None or not scenario_id.startswith(f"{owner}-"):
                errors.append(f"{change_dir.name}: {scenario_id} の所属要件が不正です")
            else:
                scenario_requirements[scenario_id] = owner
        found_requirements = set(REQUIREMENT_PATTERN.findall(content))
        found_scenarios = set(SCENARIO_PATTERN.findall(content))
        for requirement_id in found_requirements:
            if not any(
                scenario.startswith(f"{requirement_id}-")
                for scenario in found_scenarios
            ):
                errors.append(
                    f"{change_dir.name}: {requirement_id} に Scenario がありません"
                )
    if not requirements:
        errors.append(f"{change_dir.name}: 仕様に要件がありません")

    design = design_file.read_text(encoding="utf-8")
    tasks = tasks_file.read_text(encoding="utf-8")
    task_lines = tasks.splitlines()
    task_matches = [
        match for line in task_lines if (match := TASK_LINE_PATTERN.match(line))
    ]
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
            if requirement_id in traceability_requirements:
                errors.append(
                    f"{change_dir.name}: 要件トレーサビリティの {requirement_id} が重複しています"
                )
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
    test_case_ids: set[str] = set()
    pytest_references: set[str] = set()
    for row in test_cases:
        if len(row) < 8 or not TEST_CASE_ID_PATTERN.fullmatch(row[0]):
            errors.append(f"{change_dir.name}: 試験設計の試験ケース行が不正です")
            continue
        tc_id, requirement_id, scenario_id = row[:3]
        pytest_reference = row[6].strip("`")
        if tc_id in test_case_ids:
            errors.append(f"{change_dir.name}: 試験ケースID {tc_id} が重複しています")
        test_case_ids.add(tc_id)
        if requirement_id not in requirements:
            errors.append(
                f"{change_dir.name}: {tc_id} の要件 {requirement_id} は仕様に存在しません"
            )
        if scenario_id not in scenarios:
            errors.append(
                f"{change_dir.name}: {tc_id} の Scenario {scenario_id} は仕様に存在しません"
            )
        elif scenario_requirements.get(scenario_id) != requirement_id:
            errors.append(
                f"{change_dir.name}: {tc_id} の要件と {scenario_id} の所属要件が一致しません"
            )
        if not PYTEST_REFERENCE_PATTERN.fullmatch(pytest_reference):
            errors.append(
                f"{change_dir.name}: {tc_id} の pytest 実装先が不正です: {pytest_reference}"
            )
        elif (
            not (repository_root / pytest_reference.split("::")[0])
            .resolve()
            .is_relative_to(repository_root)
        ):
            errors.append(
                f"{change_dir.name}: {tc_id} の pytest 実装先がリポジトリ外です"
            )
        else:
            pytest_references.add(pytest_reference)
        scenario_cases.setdefault(scenario_id, []).append((tc_id, pytest_reference))

    for scenario_id in scenarios:
        cases = scenario_cases.get(scenario_id, [])
        if not cases:
            errors.append(f"{change_dir.name}: {scenario_id} に TC-ID がありません")
            continue

    for cases in scenario_cases.values():
        for tc_id, _pytest_reference in cases:
            has_test_task = any(
                line.lstrip().startswith("- [")
                and tc_id in TEST_CASE_ID_PATTERN.findall(line)
                and "pytest" in line
                and "tests/" in line
                for line in task_lines
            )
            if not has_test_task:
                errors.append(
                    f"{change_dir.name}: {tc_id} に対応する pytest テスト作成・実行タスクがありません"
                )
    if phase in {"implementation", "complete"}:
        errors.extend(
            check_test_collection(repository_root, pytest_references, change_dir.name)
        )
    if phase == "complete":
        if not task_matches:
            errors.append(f"{change_dir.name}: 完了検査に必要なタスクがありません")
        for line in task_lines:
            checkbox = re.match(r"^\s*-\s*\[([^\]]*)]\s*(.*)$", line)
            if checkbox and checkbox[1].strip().lower() != "x":
                errors.append(f"{change_dir.name}: 未完了タスク: {checkbox[2]}")
        errors.extend(check_acceptance(change_dir, design, repository_root))
    return errors


def check_test_collection(
    root: Path, references: set[str], change_name: str
) -> list[str]:
    """Collect referenced files once; collection does not run test bodies."""
    if not references:
        return []
    files = sorted({reference.split("::")[0] for reference in references})
    missing = [file for file in files if not (root / file).is_file()]
    if missing:
        return [
            f"{change_name}: pytest 実装ファイルが存在しません: {file}"
            for file in missing
        ]
    try:
        result = subprocess.run(  # noqa: S603 -- same interpreter, validated repository-local test files.
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "--color=no",
                "-o",
                "addopts=",
                *files,
            ],
            cwd=root,
            env={**os.environ, "PYTEST_ADDOPTS": ""},
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return [f"{change_name}: pytest 収集に失敗しました: {error}"]
    if result.returncode != 0:
        return [
            f"{change_name}: pytest 収集に失敗しました:\n{result.stdout}{result.stderr}"
        ]
    nodes = {line.strip() for line in result.stdout.splitlines() if "::" in line}
    return [
        f"{change_name}: pytest 実装先が収集されません: {reference}"
        for reference in sorted(references)
        if not any(
            node == reference or node.startswith(reference + "[") for node in nodes
        )
    ]


def check_acceptance(change_dir: Path, design: str, root: Path) -> list[str]:
    """Require one verified record and nonempty local evidence per acceptance ID."""
    errors: list[str] = []
    proposal = change_dir / "proposal.md"
    if not proposal.is_file():
        return [f"{change_dir.name}: 完了検査には proposal.md が必要です"]
    acceptance_ids: set[str] = set()
    section = markdown_section(
        proposal.read_text(encoding="utf-8"), "## 運用開始の受け入れ条件"
    )
    for line in section.splitlines():
        if not re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", line):
            continue
        match = re.fullmatch(r"- (AC-\d{3}):\s*\S.*", line)
        if match is None:
            errors.append(
                f"{change_dir.name}: 受け入れ条件には AC-ID が必要です: {line}"
            )
            continue
        acceptance_id = match[1]
        if acceptance_id in acceptance_ids:
            errors.append(
                f"{change_dir.name}: 受け入れID {acceptance_id} が重複しています"
            )
        acceptance_ids.add(acceptance_id)
    if not acceptance_ids:
        errors.append(f"{change_dir.name}: AC-ID 付き受け入れ条件がありません")
    recorded: set[str] = set()
    for row in markdown_table_rows(design, "## 受け入れ検証"):
        if len(row) != 6 or not ACCEPTANCE_ID_PATTERN.fullmatch(row[0]) or not all(row):
            errors.append(f"{change_dir.name}: 受け入れ検証の行が不正です: {row[0]}")
            continue
        acceptance_id, _scope, _method, remaining, status, evidence = row
        if acceptance_id in recorded:
            errors.append(
                f"{change_dir.name}: {acceptance_id} の受け入れ検証が重複しています"
            )
        recorded.add(acceptance_id)
        if acceptance_id not in acceptance_ids:
            errors.append(f"{change_dir.name}: 未知の受け入れID {acceptance_id}")
        if status != "検証済み" or remaining != "なし":
            errors.append(
                f"{change_dir.name}: {acceptance_id} は未検証または残る検証があります"
            )
        evidence_path = Path(evidence.strip("`"))
        resolved = (root / evidence_path).resolve()
        if evidence_path.is_absolute() or not resolved.is_relative_to(root):
            errors.append(
                f"{change_dir.name}: {acceptance_id} の証跡はリポジトリ相対パスにしてください"
            )
        elif not resolved.is_file() or not resolved.read_bytes().strip():
            errors.append(
                f"{change_dir.name}: {acceptance_id} の証跡が存在しないか空です: {evidence}"
            )
    for acceptance_id in sorted(acceptance_ids - recorded):
        errors.append(f"{change_dir.name}: {acceptance_id} の受け入れ検証がありません")
    return errors


def parse_arguments() -> argparse.Namespace:
    """Parse the change selection arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--change", help="change 名、または archive/<保存名>")
    selection.add_argument(
        "--all", action="store_true", help="すべての進行中 change を検査する"
    )
    parser.add_argument(
        "--phase",
        choices=["design", "implementation", "complete"],
        default="design",
        help="設計・実装後・完了時の検査（既定: design）",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="--all の対象にアーカイブ済み change を含める",
    )
    arguments = parser.parse_args()
    if arguments.include_archived and not arguments.all:
        parser.error("--include-archived は --all と併用してください")
    return arguments


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
        archive_root = changes_root / "archive"
        if arguments.include_archived and archive_root.is_dir():
            change_dirs.extend(path for path in archive_root.iterdir() if path.is_dir())
    errors: list[str] = []
    for change_dir in sorted(change_dirs):
        resolved = change_dir.resolve()
        if resolved == changes_root.resolve() or not resolved.is_relative_to(
            changes_root.resolve()
        ):
            errors.append(
                f"change の指定が openspec/changes 配下ではありません: {change_dir}"
            )
            continue
        errors.extend(check_change(change_dir, phase=arguments.phase))
    if errors:
        print(
            "OpenSpec traceability checks failed:", *errors, sep="\n", file=sys.stderr
        )
        return 1
    print("OpenSpec traceability checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
