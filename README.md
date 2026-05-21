# AI Project Builder Agent Demo
它模拟并实现了一个多 Agent 项目构建流水线：

1. `RequirementAnalyzerAgent`：把自然语言目标拆成痛点、用户、功能、验收标准。
2. `ArchitectureAgent`：设计模块、数据模型、文件结构和质量门禁。
3. `TaskPlannerAgent`：把项目构建拆成有依赖关系的任务。
4. `CodeBuilderAgent`：生成一个可运行的 Python 示例项目。
5. `TestReviewerAgent`：自动编译并运行单元测试。
6. `ReadmeAgent`：输出 README 和 `agent_report.json` 执行轨迹。

默认不需要任何外部依赖，也不需要 API Key。若设置 `OPENAI_API_KEY`，可以加 `--use-llm` 调用 OpenAI-compatible Chat Completions 接口增强需求分析。

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

## Actions 示例

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
