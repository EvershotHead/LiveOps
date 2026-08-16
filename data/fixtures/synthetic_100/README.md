# synthetic_100 固定样本（合成夹具）

- 100 条合成中文游戏评论，由开发 Agent 撰写，`synthetic=true`。
- 仅用于端到端管道验证、标注体系演示与评测框架测试。
- **绝不冒充真实玩家数据**；公开演示站不会将本夹具展示为“玩家洞察”。
- seed_annotations.json 为开发 Agent（强模型）的结构化种子标注，annotator_type=strong_model_seed，供 ScriptedLLM 回放与真实模型对照评测。
