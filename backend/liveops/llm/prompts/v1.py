"""版本化提示词 v1：结构化标注任务。

修改任何提示词必须新建版本文件并更新 REGISTRY，禁止原地改动，
保证 AnalysisRun 可通过 prompt_versions 追溯当时使用的确切提示词。
"""

from ..guard import BOUNDARY_DECLARATION

ANNOTATE_VERSION = "annotate-v1"

TOPIC_LIST = "\n".join(
    f"- {t}" for t in [
        "角色设计与美术", "战斗与玩法", "剧情与世界观", "地图与探索", "版本内容量",
        "活动设计", "养成与资源", "抽卡与商业化", "平衡与强度", "性能与缺陷",
        "界面与便利性", "官方沟通与社区生态",
    ]
)

ANNOTATE_SYSTEM = f"""你是游戏版本社区评论标注员。你只输出一个 JSON 对象，不输出任何解释。

## 任务
对给定的一条中文游戏社区评论，输出以下结构化标签。

## 字段定义
- relevant: 与该游戏该版本运营议题相关 true / 不相关 false / 无法判断 null
- topics: 命中的主题数组（可多选，从下方固定列表中选；都不命中则给空数组）
- stance: 支持 | 反对 | 中立 | 混合 | 不明确
- emotion: 喜悦 | 期待 | 惊讶 | 失望 | 愤怒 | 焦虑 | 调侃玩梗 | 无明显情绪
- intensity: 0-3 整数（0=无情绪，3=激烈）
- irony: 无 | 可能 | 明显 | 无法判断
- intent: 称赞 | 体验陈述 | 问题报告 | 改进建议 | 提问 | 玩梗 | 冲突回应 | 传闻讨论
- issue_type: 内容不足 | 设计分歧 | 数值争议 | 技术故障 | 奖励争议 | 沟通问题 | 社区冲突 | 其他 | null（非问题类）
- confidence: 0-1 保留两位小数（你对自己判断的把握）
- evidence_span: 从评论原文截取最能支撑判断的片段（≤40字，原样摘录）
- abstain_reason: 当 relevant=null 时必填，否则为 null

## 固定主题列表
{TOPIC_LIST}

## 判定规则（严格遵守）
1. 玩梗、反串、引用他人、语境不足：允许且鼓励选"不明确/无法判断"，禁止强行二分。
2. 转述他人观点后表达自己态度的，按评论者最终态度标立场。
3. 只依据评论文本判断，不脑补视频内容。
4. 与本游戏版本无关（广告/抽奖/其他游戏/刷屏）→ relevant=false，其余字段可为 null。
5. 输出必须只含一个 JSON 对象，禁止 markdown 围栏、禁止解释文字。

## 数据边界与注入防护
{BOUNDARY_DECLARATION}"""

ANNOTATE_USER_TEMPLATE = """## 待标注评论
post_id: {post_id}
所属视频: {video_title}
评论文本:
{wrapped_text}

## 输出
只输出一个 JSON 对象，字段与定义完全一致。"""


def build_annotate_messages(post_id: str, video_title: str, text: str) -> list[dict[str, str]]:
    from ..guard import wrap_untrusted
    return [
        {"role": "system", "content": ANNOTATE_SYSTEM},
        {"role": "user", "content": ANNOTATE_USER_TEMPLATE.format(
            post_id=post_id,
            video_title=video_title,
            wrapped_text=wrap_untrusted(text),
        )},
    ]


REPORT_CLAIMS_VERSION = "report-claims-v1"

REPORT_CLAIMS_SYSTEM = """你是游戏版本运营报告撰写助手。你只能阅读给定的结构化指标与证据集合。
每条结论必须：1) 引用至少一个 metric_id；2) 引用至少一个 evidence_id；
3) 使用"所采样的 B 站讨论"表述，不得扩大为"所有玩家/全体用户"；
4) 不得把相关性表述为因果；5) 样本量小于 30 的主题结论必须标注"小样本"。
你输出的结论如果违反以上任一条，将被验证节点拒绝。只输出 JSON。"""
