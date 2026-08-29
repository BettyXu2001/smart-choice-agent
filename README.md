# Choice Agent V2

Choice Agent V2 是一个 Python 多 Agent 决策系统，饮食是第一个完整领域。项目以
原 diet-agent 的功能为迁移基线，同时加入候选项、约束、评价标准、证据、稳定排序
和权衡解释等通用决策能力。

## 当前能力

- 意图、理解、澄清、候选、调整、计划、审查、解释、风险和评估 Agent；
- 单餐推荐、多轮澄清、换一批和三餐计划；
- 个人餐食库和公共餐食库；
- 硬约束过滤和七维确定性评分；
- 会话、消息、推荐历史、反馈、DecisionState、Evidence 和 Agent Run 持久化；
- 完整请求 Trace、人工标注和规则/可选 LLM 评估；
- 兼容原饮食项目主要 API 和前端页面；
- 无模型密钥时使用规则 Agent 完整运行。

## 技术结构

~~~text
FastAPI / Static Web
  -> DietOrchestrator
    -> Specialized Agents
      -> Deterministic Decision Engine
        -> Diet Domain Plugin
          -> SQLAlchemy / SQLite
~~~

多 Agent 负责理解、澄清、候选获取、计划、审查和解释。硬约束、评分、排序和数据隔离
由普通 Python 代码执行。每次 Agent 运行都记录独立输入、输出、耗时、状态和错误。

## 本地运行

Python 要求 3.10 或更高版本。

~~~powershell
python -m pip install -e .
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
~~~

未安装项目包时，可直接设置源码路径：

~~~powershell
$env:PYTHONPATH = "src"
python scripts/init_db.py
python -m uvicorn choice_agent.main:app --host 127.0.0.1 --port 8000
~~~

打开 http://127.0.0.1:8000/。API 文档位于 http://127.0.0.1:8000/docs。

## 模型配置

默认 CHOICE_AGENT_ENABLE_LLM=false，系统使用确定性规则 Agent。复制 .env.example
中的变量到运行环境并配置 API Key 后，可启用 OpenAI-compatible Chat Completions 接口。
模型调用失败时，意图和解释 Agent 会使用本地规则结果，不影响确定性决策引擎。

## 数据

默认数据库为项目根目录下的 choice_agent.db。首次启动会创建全部表，并从打包的
legacy_diet_db.sql 幂等导入原项目的槽位选项和餐食数据。旧项目和旧数据库不会被写入。

## 测试

~~~powershell
python -m pytest
python -m compileall -q src scripts
~~~

## 主要目录

- src/choice_agent/agents：独立 Agent 和运行协议；
- src/choice_agent/orchestration：多 Agent 状态机；
- src/choice_agent/decision：通用确定性决策引擎；
- src/choice_agent/domains/diet：饮食领域规则和数据；
- src/choice_agent/api：兼容 API 与通用决策查询；
- src/choice_agent/static：迁移后的前端；
- tests：规则、引擎、编排、Trace 和数据测试；
- adr：Research 和 Plan。

