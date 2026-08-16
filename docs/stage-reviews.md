# 阶段审查报告

## 阶段 A（地基 + 100 条纵向切片）— 2026-08-16 完成

### 测试证据
- `uv run python -m pytest tests/ -q` → **132 passed**（0 failed）
- 端到端：`uv run liveops run --fixture synthetic_100` → status=completed，
  有效相关评论 94/100，弃权 1（注入样本 p100 正确弃权），无关 3，重复 1；
  结论验证通过（5 条结论全部引用 metric_id + evidence_id）。

### 完成门核验
| 门 | 结果 |
|---|---|
| Schema 六对象 + roundtrip/校验测试 | ✅ 18 用例 |
| 标签手册 v1.0 + 枚举一致 | ✅ docs/labeling-guide.md |
| 导入器四格式 + 损坏/空/超长 | ✅ 23 用例 |
| LLM 客户端（OpenAI兼容/Ollama/Mock）+ 缓存 + 重试 + 注入防护 | ✅ 19 用例（含注入重放） |
| LangGraph 状态图 + 阶段断点续跑 + 单任务锁 | ✅ 17 用例（kill-恢复、409 锁、hash 不一致拒绝） |
| 规范化（清洗/去重/时间窗/垃圾标记） | ✅ 19 用例 |
| 嵌入聚类降级链（bge-m3→small→hash） | ✅ 11 用例 |
| 指标库 9 项 + 权重敏感性 | ✅ 18 用例（手工精确断言） |
| 100 条固定样本纵向切片 | ✅ 7 用例 + CLI 实跑 |
| P0 文档（PRD/采样协议/合规） | ✅ 三份 |

### 已知限制（如实记录）
1. 评测框架（金标准 F1/Kappa/ECE）在阶段 C 交付；当前无"真实模型 vs 种子"对比数字。
2. 报告结论为程序化生成（未接 LLM 润色层——LLM 润色为可选增强，默认关闭保证可复现）。
3. 嵌入质量当前为 hash-degraded（未安装 sentence-transformers 重依赖）；真实数据阶段将安装 bge-m3。
4. 前端仅有脚手架（页面在阶段 D）。

### 与方案的偏差
- 近重复去重用「长度分桶 + 序列相似度」替代纯 SimHash（短中文评论 SimHash 区分度不足）；simhash 保留为工具函数。
- LangGraph 用于图结构声明与校验，执行循环为自研阶段执行器（磁盘级断点）——比 LangGraph 内置 checkpointer 更可审计，节点函数两条路径共用。
