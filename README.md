# LiveOps Community Intelligence

**游戏版本社区洞察与运营复盘系统** —— 固定、可复现、可审计的 B 站社区评论分析流水线 + 运营工作台。

> 口径：全部结论仅描述**所采样的 B 站讨论**，不代表所有玩家。

## 它是什么

```
公开数据(受限采样/文件导入) → Canonical Schema 规范化 → 相关性过滤
  → 主题/立场/情绪/反讽/诉求标注（LLM 结构化 + 强模型种子 + 人工复核两层金标）
  → Python 量化聚合（LLM 不碰数值） → 原文证据回溯 → 版本复盘报告（结论验证节点把关）
```

**不是**：通用情感分析工具 / LLM 评论总结套壳 / 实时舆情监控。

## 快速开始

### 本地完整模式（一键）

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\start-local.ps1
# 或 Git Bash
bash scripts/start-local.sh
```

打开 http://localhost:3000。后端 FastAPI :8000，前端 Next.js :3000。

- 首次：`cd backend && uv sync --extra dev --extra embed`；`cd frontend && pnpm install`
- 真实 LLM 标注：复制 `.env.example` 为 `.env`，填写 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`（OpenAI 兼容，预留 Ollama 适配），重启即可。未配置密钥时系统以种子回放/演示数据运行。
- 已内置两个真实案例 run：`runs/full-genshin-6.8`、`runs/full-wuthering-3.5`（全量标注，在「数据与任务」页选择查看）。

### 公开演示模式（无密钥只读，开箱即看）

```bash
bash scripts/start-demo.sh          # 一键：构建静态站 + 本地服务 + 打开浏览器
# 或指定端口: bash scripts/start-demo.sh 8080
```

首次会自动构建（约 1-2 分钟），之后秒开。演示数据为预计算 JSON（`demo/public-data/`，已匿名化 + 泄漏扫描），左上角可切换《原神 6.8》/《鸣潮 3.5》。这是「无需任何密钥即可查看完整样例」的推荐入口。

## 复现主要结果

```bash
cd backend
uv run python -m pytest tests/ -q            # 208+ 测试
uv run python tools/collect_bilibili.py --study genshin68   # 受限公开采样（断点续采）
uv run python tools/freeze_study.py --study genshin-6.8     # 配额校验+冻结
uv run python tools/run_seed_analysis.py    # 双游戏全量分析+评测
uv run python tools/export_demo.py          # 演示导出（含泄漏扫描断言）
```

## 仓库结构

| 目录 | 说明 |
|---|---|
| `backend/liveops` | Schema / 导入器 / 采集器 / 规范化 / 嵌入聚类 / LLM客户端(注入防护) / LangGraph Harness / 指标库 / 评测 / FastAPI |
| `backend/tests` | Pytest：导入/Schema/去重/窗口/指标公式/异常输出/断点/注入/损坏文件/空数据/超长/限流/密钥缺失 |
| `backend/tools` | 采集/冻结/抽样/种子合并/全量分析/演示导出 |
| `frontend/src` | 9 页面运营工作台（Next.js + Tailwind + shadcn 风格 + ECharts） |
| `data/raw` | 原始采集（gitignore，含未匿名数据）→ `frozen/` 冻结样本 |
| `data/gold` | 种子金标 800 条（400×2） |
| `runs/<run_id>` | 每次分析：manifest（模型/提示词版本/代码SHA/数据集hash/成本/耗时）+ 阶段断点 + 指标 + 报告 |
| `demo/public-data` | 匿名化演示数据（泄漏扫描强制通过） |
| `docs` | PRD / 采样协议 / 合规说明 / 标签手册 / 评测报告 / 两份版本复盘 / 架构图 |

## 文档索引

- [PRD](docs/prd.md) · [采样协议与版本锁定](docs/sampling-protocol.md) · [数据合规说明](docs/compliance.md)
- [标签手册 v1.0](docs/labeling-guide.md) · [架构图](docs/architecture.md)
- [评测报告（真实数字）](docs/evaluation-report.md)
- [原神 6.8 复盘](docs/case-genshin-6.8.md) · [鸣潮 3.5 复盘](docs/case-wuthering-3.5.md)
- [阶段审查报告](docs/stage-reviews.md)

## 核心设计约束

1. **LLM 永不计算指标**：9 项指标（主题占比/净支持率/争议度/趋势/互动/持续性/UGC扩散/问题优先级/机会值）全部 Python 精确实现，测试用手工 fixture 断言到小数位。
2. **不可信数据边界**：社区文本用 `<untrusted_community_text>` 包裹 + 注入防护声明 + 严格 JSON Schema + 一次修复重试 + 弃权路径；注入语料测试保证输出仍是合法标签。
3. **每个结论可回溯**：metric_id + evidence_id 双引用，验证节点拒绝过度泛化（"所有玩家"）、因果表述与小样本无标注结论。
4. **诚实口径**：受限采样配额缺口、34% 弃权率、向量基线弱数字、LLM 层"未测量"全部如实展示；组合分数明示为可配置排序规则并提供 ±10% 权重敏感性。
5. **单机串行 + 阶段断点**：文件锁保证单任务；kill 后按阶段产物 hash 续跑（有测试覆盖）。

## 测试与 QA

- 后端：`uv run python -m pytest tests/ -q`（208+ 用例）
- 前端：`pnpm exec playwright test`（演示站 9 页面 × 桌面/移动：渲染/图表非空/无横向溢出/证据链接/只读校验）
- 采集护栏有专门测试：风控码硬停不重试、令牌桶间隔、journal 断点续采、配额校验规则。

## 合规底线（摘要）

仅公开内容、不登录不绕风控（412/-352 硬停）、原始 UID 不落盘（HMAC 不可逆匿名）、公开导出强制泄漏扫描、合成数据显式标记。详见 [docs/compliance.md](docs/compliance.md)。

## 已知限制（如实）

1. 受限公开采样未达 4,000-5,000 条/游戏配额（未登录会话仅首页评论+楼中楼可见）；补足路径：自行导出评论 → 文件导入（正式能力）。
2. 人工金标层待用户复核（工作台已就绪）；双人 Kappa 未计算。
3. LLM 标注质量未测量（密钥待配置）；当前数字为管道校验与向量基线。
