#!/usr/bin/env python3
"""
AI Project Builder Agent Demo

A runnable, dependency-free multi-agent demo for project construction:
1. RequirementAnalyzerAgent: turns a high-level goal into pain points, user stories, and acceptance criteria.
2. ArchitectureAgent: designs modules, data model, and file structure.
3. TaskPlannerAgent: decomposes work into ordered engineering tasks.
4. CodeBuilderAgent: generates a small but runnable Python project.
5. TestReviewerAgent: compiles generated code and runs its unit tests.
6. ReadmeAgent: writes documentation and an agent execution report.

Optional LLM mode:
- Set OPENAI_API_KEY and run with --use-llm to let the analyzer call an OpenAI-compatible Chat Completions endpoint.
- Default mode is fully offline and deterministic so the demo works in CI/GitHub Actions without secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# -----------------------------
# Utility functions
# -----------------------------


def now_ms() -> int:
    return int(time.time() * 1000)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def safe_slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", "-", text.strip()).strip("-")
    return slug[:max_len] or "generated-project"


def run_command(command: List[str], cwd: Path, timeout: int = 20) -> Dict[str, Any]:
    started = now_ms()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            timeout=timeout,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return {
            "command": " ".join(command),
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "duration_ms": now_ms() - started,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "cwd": str(cwd),
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": f"Command timed out after {timeout}s",
            "duration_ms": now_ms() - started,
        }


# -----------------------------
# Optional OpenAI-compatible client
# -----------------------------


class OptionalLLMClient:
    """Tiny OpenAI-compatible Chat Completions client using only stdlib."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def complete_json(self, system: str, user: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError) as exc:
            return {
                "llm_error": str(exc),
                "fallback_notice": "LLM call failed; deterministic local planning was used instead.",
            }


# -----------------------------
# Agent framework
# -----------------------------


@dataclass
class AgentStep:
    name: str
    summary: str
    output: Dict[str, Any]
    duration_ms: int


@dataclass
class AgentContext:
    goal: str
    workspace: Path
    project_dir: Path
    use_llm: bool = False
    steps: List[AgentStep] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)

    def record(self, name: str, summary: str, output: Dict[str, Any], started_ms: int) -> None:
        self.steps.append(
            AgentStep(
                name=name,
                summary=summary,
                output=output,
                duration_ms=now_ms() - started_ms,
            )
        )
        self.state[name] = output


class BaseAgent:
    name = "BaseAgent"

    def run(self, ctx: AgentContext) -> Dict[str, Any]:
        raise NotImplementedError

    def __call__(self, ctx: AgentContext) -> None:
        started = now_ms()
        output = self.run(ctx)
        summary = output.get("summary", f"{self.name} completed")
        ctx.record(self.name, summary, output, started)
        print(f"[OK] {self.name}: {summary}")


class RequirementAnalyzerAgent(BaseAgent):
    name = "RequirementAnalyzerAgent"

    def __init__(self, llm: OptionalLLMClient) -> None:
        self.llm = llm

    def run(self, ctx: AgentContext) -> Dict[str, Any]:
        llm_result: Optional[Dict[str, Any]] = None
        if ctx.use_llm and self.llm.enabled:
            system = (
                "You are a senior product and engineering agent. "
                "Return strict JSON with keys: pain_points, users, features, acceptance_criteria, risks."
            )
            user = f"Project goal: {ctx.goal}\nAnalyze it for a small runnable software demo."
            llm_result = self.llm.complete_json(system, user)

        if llm_result and "pain_points" in llm_result:
            result = dict(llm_result)
            result["source"] = "llm"
        else:
            goal = ctx.goal
            result = {
                "source": "deterministic-fallback",
                "pain_points": [
                    "需求描述经常停留在自然语言，工程团队需要反复澄清范围、边界和验收标准。",
                    "从需求到代码骨架、测试用例、README 的链路割裂，容易遗漏质量检查。",
                    "项目初期缺少可运行样例，评审者无法快速判断方案是否真的可落地。",
                ],
                "users": ["产品负责人", "后端/全栈工程师", "项目评审者"],
                "features": [
                    f"围绕目标生成项目蓝图：{goal}",
                    "自动拆解模块、数据模型、接口和文件结构。",
                    "生成可运行 Python 示例项目，并自动执行单元测试。",
                    "产出 agent 执行轨迹报告，便于复盘每个 Agent 的输入输出。",
                ],
                "acceptance_criteria": [
                    "一条命令即可生成项目文件。",
                    "生成项目必须能通过 python -m unittest。",
                    "报告中必须包含需求分析、架构设计、任务拆解、测试结果。",
                    "不依赖外部包，默认可在 GitHub Actions 或本地离线执行。",
                ],
                "risks": [
                    "真实业务代码生成需要更严格的安全审查和人工 code review。",
                    "LLM 结果可能不稳定，因此 demo 默认保留 deterministic fallback。",
                ],
            }
            if llm_result and "llm_error" in llm_result:
                result["llm_error"] = llm_result["llm_error"]

        result["summary"] = "extracted pain points, users, features, acceptance criteria"
        return result


class ArchitectureAgent(BaseAgent):
    name = "ArchitectureAgent"

    def run(self, ctx: AgentContext) -> Dict[str, Any]:
        req = ctx.state["RequirementAnalyzerAgent"]
        architecture = {
            "style": "modular single-package Python CLI + library",
            "modules": [
                {
                    "name": "project_app.py",
                    "responsibility": "Domain model, in-memory board, JSON persistence, and CLI entrypoint.",
                },
                {
                    "name": "tests/test_project_app.py",
                    "responsibility": "Unit tests covering creation, status transition, persistence, and CLI behavior.",
                },
                {
                    "name": "README.md",
                    "responsibility": "Usage guide for reviewers and GitHub visitors.",
                },
            ],
            "data_model": {
                "Task": {
                    "id": "integer primary key",
                    "title": "short requirement or engineering task",
                    "owner": "responsible role",
                    "status": "todo | doing | done",
                }
            },
            "quality_gates": [
                "compileall passes",
                "python -m unittest discovers and passes tests",
                "agent_report.json is generated for traceability",
            ],
            "mapped_features": req.get("features", []),
            "summary": "designed module structure, data model, and quality gates",
        }
        return architecture


class TaskPlannerAgent(BaseAgent):
    name = "TaskPlannerAgent"

    def run(self, ctx: AgentContext) -> Dict[str, Any]:
        tasks = [
            {
                "id": 1,
                "title": "Analyze requirement and define acceptance criteria",
                "depends_on": [],
                "agent": "RequirementAnalyzerAgent",
            },
            {
                "id": 2,
                "title": "Design architecture and data model",
                "depends_on": [1],
                "agent": "ArchitectureAgent",
            },
            {
                "id": 3,
                "title": "Generate project source code and tests",
                "depends_on": [2],
                "agent": "CodeBuilderAgent",
            },
            {
                "id": 4,
                "title": "Run compile and unit-test quality gates",
                "depends_on": [3],
                "agent": "TestReviewerAgent",
            },
            {
                "id": 5,
                "title": "Write README and agent execution report",
                "depends_on": [4],
                "agent": "ReadmeAgent",
            },
        ]
        return {
            "tasks": tasks,
            "critical_path": [task["id"] for task in tasks],
            "summary": f"planned {len(tasks)} dependent engineering tasks",
        }


class CodeBuilderAgent(BaseAgent):
    name = "CodeBuilderAgent"

    def run(self, ctx: AgentContext) -> Dict[str, Any]:
        if ctx.project_dir.exists():
            shutil.rmtree(ctx.project_dir)
        ctx.project_dir.mkdir(parents=True, exist_ok=True)
        (ctx.project_dir / "src").mkdir(parents=True, exist_ok=True)
        (ctx.project_dir / "tests").mkdir(parents=True, exist_ok=True)

        project_app = r'''
"""Generated demo project: a tiny project task board.

The file is intentionally simple and dependency-free so it can run in any
standard Python 3.9+ environment.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List

VALID_STATUS = {"todo", "doing", "done"}


@dataclass
class Task:
    id: int
    title: str
    owner: str = "agent"
    status: str = "todo"

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Task title cannot be empty")
        if self.status not in VALID_STATUS:
            raise ValueError(f"Invalid status: {self.status}")


class ProjectBoard:
    def __init__(self, tasks: Iterable[Task] | None = None) -> None:
        self.tasks: List[Task] = list(tasks or [])

    def add(self, title: str, owner: str = "agent") -> Task:
        next_id = max([task.id for task in self.tasks], default=0) + 1
        task = Task(id=next_id, title=title, owner=owner)
        self.tasks.append(task)
        return task

    def set_status(self, task_id: int, status: str) -> Task:
        if status not in VALID_STATUS:
            raise ValueError(f"Invalid status: {status}")
        for task in self.tasks:
            if task.id == task_id:
                task.status = status
                return task
        raise KeyError(f"Task not found: {task_id}")

    def summary(self) -> dict:
        counts = {status: 0 for status in sorted(VALID_STATUS)}
        for task in self.tasks:
            counts[task.status] += 1
        return {"total": len(self.tasks), "by_status": counts}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(task) for task in self.tasks], ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ProjectBoard":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(Task(**item) for item in raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tiny generated project board")
    parser.add_argument("action", choices=["add", "done", "list", "summary"])
    parser.add_argument("value", nargs="?", help="task title for add; task id for done")
    parser.add_argument("--owner", default="agent")
    parser.add_argument("--db", default="project_board.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db_path = Path(args.db)
    board = ProjectBoard.load(db_path)

    if args.action == "add":
        if not args.value:
            raise SystemExit("add requires a task title")
        task = board.add(args.value, owner=args.owner)
        board.save(db_path)
        print(json.dumps(asdict(task), ensure_ascii=False))
        return 0

    if args.action == "done":
        if not args.value:
            raise SystemExit("done requires a task id")
        task = board.set_status(int(args.value), "done")
        board.save(db_path)
        print(json.dumps(asdict(task), ensure_ascii=False))
        return 0

    if args.action == "list":
        print(json.dumps([asdict(task) for task in board.tasks], ensure_ascii=False, indent=2))
        return 0

    if args.action == "summary":
        print(json.dumps(board.summary(), ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
'''
        test_code = r'''
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_app import ProjectBoard, Task


class ProjectBoardTests(unittest.TestCase):
    def test_add_and_summary(self):
        board = ProjectBoard()
        board.add("Analyze requirements", owner="pm-agent")
        board.add("Generate tests", owner="qa-agent")
        board.set_status(1, "done")
        self.assertEqual(board.summary()["total"], 2)
        self.assertEqual(board.summary()["by_status"]["done"], 1)
        self.assertEqual(board.summary()["by_status"]["todo"], 1)

    def test_task_validation(self):
        with self.assertRaises(ValueError):
            Task(id=1, title="   ")
        with self.assertRaises(ValueError):
            Task(id=2, title="Valid title", status="blocked")

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "board.json"
            board = ProjectBoard()
            board.add("Persist generated result")
            board.save(db)
            loaded = ProjectBoard.load(db)
            self.assertEqual(loaded.tasks[0].title, "Persist generated result")

    def test_cli_add_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "board.json"
            app = ROOT / "src" / "project_app.py"
            add = subprocess.run(
                [sys.executable, str(app), "add", "Ship demo", "--db", str(db)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(add.returncode, 0, add.stderr)
            payload = json.loads(add.stdout)
            self.assertEqual(payload["title"], "Ship demo")

            summary = subprocess.run(
                [sys.executable, str(app), "summary", "--db", str(db)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertEqual(json.loads(summary.stdout)["total"], 1)


if __name__ == "__main__":
    unittest.main()
'''
        gitignore = """
__pycache__/
*.py[cod]
project_board.json
.agent_build/
.env
"""
        generated_readme = f"""
# Generated Project: AI-built Project Board

This project was generated by `agent_demo.py` from the goal below:

> {ctx.goal}

## Run

```bash
python src/project_app.py add "Analyze requirements" --owner pm-agent
python src/project_app.py summary
python -m unittest discover -s tests -v
```

## What it demonstrates

- A small but complete Python application generated by a multi-agent pipeline.
- Domain model validation, JSON persistence, CLI interface, and unit tests.
- Traceability through `agent_report.json` in the parent demo workspace.
"""
        write_text(ctx.project_dir / "src" / "project_app.py", project_app)
        write_text(ctx.project_dir / "tests" / "test_project_app.py", test_code)
        write_text(ctx.project_dir / "README.md", generated_readme)
        write_text(ctx.project_dir / ".gitignore", gitignore)

        files = sorted(str(path.relative_to(ctx.project_dir)) for path in ctx.project_dir.rglob("*") if path.is_file())
        return {
            "project_dir": str(ctx.project_dir),
            "files": files,
            "summary": f"generated {len(files)} project files",
        }


class TestReviewerAgent(BaseAgent):
    name = "TestReviewerAgent"

    def run(self, ctx: AgentContext) -> Dict[str, Any]:
        compile_result = run_command([sys.executable, "-m", "compileall", "-q", "src", "tests"], cwd=ctx.project_dir)
        test_result = run_command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ctx.project_dir)
        passed = compile_result["returncode"] == 0 and test_result["returncode"] == 0
        return {
            "passed": passed,
            "quality_gates": {
                "compileall": compile_result,
                "unittest": test_result,
            },
            "summary": "quality gates passed" if passed else "quality gates failed",
        }


class ReadmeAgent(BaseAgent):
    name = "ReadmeAgent"

    def run(self, ctx: AgentContext) -> Dict[str, Any]:
        report = {
            "goal": ctx.goal,
            "project_dir": str(ctx.project_dir),
            "use_llm": ctx.use_llm,
            "steps": [step.__dict__ for step in ctx.steps],
        }
        report_path = ctx.workspace / "agent_report.json"
        write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))

        markdown_steps = "\n".join(
            f"| {index + 1} | {step.name} | {step.summary} | {step.duration_ms} ms |"
            for index, step in enumerate(ctx.steps)
        )
        root_readme = f"""
# AI Project Builder Agent Demo

Goal:

> {ctx.goal}

## Agent pipeline

| # | Agent | Result | Duration |
|---:|---|---|---:|
{markdown_steps}

## Generated output

- Generated project: `{ctx.project_dir}`
- Trace report: `{report_path}`

## Verify generated project

```bash
cd {ctx.project_dir}
python -m unittest discover -s tests -v
python src/project_app.py add "Write README" --owner doc-agent
python src/project_app.py summary
```
"""
        write_text(ctx.workspace / "RUN_RESULT.md", root_readme)
        return {
            "report_path": str(report_path),
            "run_result_path": str(ctx.workspace / "RUN_RESULT.md"),
            "summary": "wrote trace report and run instructions",
        }


class MultiAgentOrchestrator:
    def __init__(self, use_llm: bool = False) -> None:
        self.llm = OptionalLLMClient()
        self.agents: List[BaseAgent] = [
            RequirementAnalyzerAgent(self.llm),
            ArchitectureAgent(),
            TaskPlannerAgent(),
            CodeBuilderAgent(),
            TestReviewerAgent(),
            ReadmeAgent(),
        ]
        self.use_llm = use_llm

    def run(self, goal: str, workspace: Path) -> AgentContext:
        project_dir = workspace / "generated_project"
        workspace.mkdir(parents=True, exist_ok=True)
        ctx = AgentContext(goal=goal, workspace=workspace, project_dir=project_dir, use_llm=self.use_llm)

        print("\n=== AI Project Builder Agent Demo ===")
        print(f"Goal: {goal}")
        if self.use_llm:
            if self.llm.enabled:
                print(f"LLM mode: enabled ({self.llm.model}, {self.llm.base_url})")
            else:
                print("LLM mode requested, but OPENAI_API_KEY is not set. Using deterministic fallback.")
        else:
            print("LLM mode: off. Using deterministic fallback for reproducible demo.")
        print()

        for agent in self.agents:
            agent(ctx)

        reviewer = ctx.state.get("TestReviewerAgent", {})
        if not reviewer.get("passed"):
            raise SystemExit("Generated project failed quality gates. See agent_report.json for details.")

        print("\n=== Done ===")
        print(f"Generated project: {ctx.project_dir}")
        print(f"Trace report:       {ctx.workspace / 'agent_report.json'}")
        print(f"Run result:         {ctx.workspace / 'RUN_RESULT.md'}")
        return ctx


DEFAULT_GOAL = (
    "构建一个 AI Agent 辅助项目初始化工具：输入项目目标后，自动完成需求分析、架构设计、"
    "任务拆解、代码骨架生成、测试运行和 README 生成。"
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Runnable multi-agent project builder demo")
    parser.add_argument("--goal", default=DEFAULT_GOAL, help="High-level project goal")
    parser.add_argument("--workspace", default=".agent_build", help="Output workspace")
    parser.add_argument("--use-llm", action="store_true", help="Use OpenAI-compatible API if OPENAI_API_KEY is set")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    orchestrator = MultiAgentOrchestrator(use_llm=args.use_llm)
    orchestrator.run(goal=args.goal, workspace=Path(args.workspace).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
