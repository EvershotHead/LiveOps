# 架构图（mermaid）

## 分析 Harness（受约束状态图）

```mermaid
flowchart TD
    A[数据来源<br/>受限公开采样 / 文件导入] --> B[Canonical Schema 校验<br/>StudyConfig/ContentItem/CommunityPost]
    B --> C[normalize 规范化<br/>清洗/去重/时间窗/垃圾标记]
    C --> D[relevance_filter 规则预筛]
    D --> E[embed_cluster<br/>bge-m3 → small → hash 降级链<br/>主题质心先验 + 新兴主题候选]
    E --> F[annotate_cheap<br/>低成本 LLM 结构化标注<br/>温度0/严格JSON/注入防护/响应缓存]
    F --> G[route_review 复核路由<br/>低置信/反讽/P95互动/审计5%]
    G --> H[annotate_strong 强模型复核]
    H --> I[await_human 人工审核工作台<br/>字段级diff留痕]
    I --> J[aggregate Python 量化聚合<br/>9项指标+权重敏感性]
    J --> K[report 程序化结论<br/>metric_id+evidence_id 双引用]
    K --> L[verify 结论验证节点<br/>禁过度泛化/禁因果/小样本标注]
    L -->|通过| M[报告导出 HTML→打印PDF]
    L -->|拒绝| K
    J -.断点续跑（阶段产物hash）.- C
```

## 数据流与产物

```mermaid
flowchart LR
    subgraph 采集（合规护栏）
        S1[搜索/元数据/评论接口<br/>限速≥2.5s] --> S2[journal 断点续采]
        S2 --> S3{风控码 -412/-352?}
        S3 -- 是 --> S4[硬停·不重试·转导入模式]
        S3 -- 否 --> S5[立即 HMAC 匿名化<br/>原始UID不落盘]
    end
    subgraph 分析任务（单机串行·文件锁）
        R1[manifest.json<br/>数据集hash/模型/提示词版本/代码SHA/成本] --> R2[normalized 阶段产物]
        R2 --> R3[annotations] --> R4[human_overrides.jsonl] --> R5[metrics.json]
        R5 --> R6[report.html + claims + verify]
    end
    subgraph 交付
        D1[本地模式 FastAPI+Next.js] --> D2[公开演示 静态导出<br/>匿名化+泄漏扫描断言]
    end
    S5 --> R1
    R6 --> D1 --> D2
```

## 前端页面（紧凑运营工作台）

```mermaid
flowchart TD
    U[数据与任务<br/>导入向导/任务列表/断点状态] --> V[总览<br/>覆盖/分布/风险机会]
    V --> W[版本时间线<br/>T0三段窗口]
    W --> X[主题洞察<br/>指标矩阵/散点]
    X --> Y[社区争议<br/>冲突排序/观点矩阵/证据]
    Y --> Z[双游戏对照<br/>每千条归一化/差异提示]
    Z --> E2[证据与审核<br/>原文回溯/标注工作台]
    E2 --> F2[模型评测<br/>F1/未测量/ECE/弃权]
    F2 --> G2[运营报告<br/>打印PDF]
```
