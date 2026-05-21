# AI Project Builder Agent Demo

这是一个可以直接放进 GitHub 仓库的最小可运行 Demo，用来展示“AI Agent 辅助项目构建”的核心链路。

它模拟并实现了一个多 Agent 项目构建流水线：

1. `RequirementAnalyzerAgent`：把自然语言目标拆成痛点、用户、功能、验收标准。
2. `ArchitectureAgent`：设计模块、数据模型、文件结构和质量门禁。
3. `TaskPlannerAgent`：把项目构建拆成有依赖关系的任务。
4. `CodeBuilderAgent`：生成一个可运行的 Python 示例项目。
5. `TestReviewerAgent`：自动编译并运行单元测试。
6. `ReadmeAgent`：输出 README 和 `agent_report.json` 执行轨迹。

默认不需要任何外部依赖，也不需要 API Key，适合评审者一条命令复现。若设置 `OPENAI_API_KEY`，可以加 `--use-llm` 调用 OpenAI-compatible Chat Completions 接口增强需求分析。

## 快速开始

```bash
git clone <your-repo-url>
cd ai-project-builder-agent-demo
python agent_demo.py
```

运行成功后会生成：

```text
.agent_build/
├── RUN_RESULT.md
├── agent_report.json
└── generated_project/
    ├── README.md
    ├── src/project_app.py
    └── tests/test_project_app.py
```

验证生成项目：

```bash
cd .agent_build/generated_project
python -m unittest discover -s tests -v
python src/project_app.py add "完成需求分析" --owner pm-agent
python src/project_app.py summary
```

## 自定义目标

```bash
python agent_demo.py --goal "构建一个用于自动生成项目脚手架、单元测试和部署说明的 AI Agent"
```

## 可选：启用真实 LLM

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
# 如使用兼容接口，可设置：export OPENAI_BASE_URL="https://your-compatible-endpoint/v1"
python agent_demo.py --use-llm
```

没有 Key 时程序会自动回退到 deterministic fallback，保证 CI 和本地演示稳定通过。

## GitHub Actions 示例

可以把下面内容保存为 `.github/workflows/demo.yml`：

```yaml
name: agent-demo
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: python agent_demo.py
      - run: python -m unittest discover -s .agent_build/generated_project/tests -v
```

## 适合在申请材料中强调的点

- 不是单轮 Prompt，而是多 Agent 协作：需求分析、架构设计、任务规划、代码生成、测试审查、文档生成。
- 包含长链路闭环：自然语言目标 -> 结构化需求 -> 架构 -> 任务 -> 代码 -> 测试 -> 报告。
- 默认可离线运行，降低评审复现成本；可选接入真实 LLM，展示扩展能力。
- `agent_report.json` 保存每个 Agent 的输出，便于审计和复盘。
