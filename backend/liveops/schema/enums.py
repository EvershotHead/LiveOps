"""标签体系枚举 —— 与 docs/labeling-guide.md 一一对应。

修改本文件必须递增 LABEL_SET_VERSION，并同步修订标签手册，
AnalysisRun 会记录该版本以保证可审计性。
"""

from enum import Enum

LABEL_SET_VERSION = "v1.0"

# ---------- 主题（多标签） ----------
FIXED_TOPICS = [
    "角色设计与美术",
    "战斗与玩法",
    "剧情与世界观",
    "地图与探索",
    "版本内容量",
    "活动设计",
    "养成与资源",
    "抽卡与商业化",
    "平衡与强度",
    "性能与缺陷",
    "界面与便利性",
    "官方沟通与社区生态",
]

NEW_TOPIC_PREFIX = "new:"


def is_valid_topic(t: str) -> bool:
    """固定主题或新兴主题占位（new:<cluster_id>）。"""
    if t in FIXED_TOPICS:
        return True
    return t.startswith(NEW_TOPIC_PREFIX) and len(t) > len(NEW_TOPIC_PREFIX)


class Stance(str, Enum):
    SUPPORT = "支持"
    OPPOSE = "反对"
    NEUTRAL = "中立"
    MIXED = "混合"
    UNCLEAR = "不明确"


class Emotion(str, Enum):
    JOY = "喜悦"
    ANTICIPATION = "期待"
    SURPRISE = "惊讶"
    DISAPPOINTMENT = "失望"
    ANGER = "愤怒"
    ANXIETY = "焦虑"
    BANTER = "调侃玩梗"
    NONE = "无明显情绪"


class Irony(str, Enum):
    NONE = "无"
    POSSIBLE = "可能"
    OBVIOUS = "明显"
    UNDETERMINABLE = "无法判断"


class Intent(str, Enum):
    PRAISE = "称赞"
    EXPERIENCE = "体验陈述"
    ISSUE_REPORT = "问题报告"
    SUGGESTION = "改进建议"
    QUESTION = "提问"
    MEME = "玩梗"
    CONFLICT_RESPONSE = "冲突回应"
    RUMOR = "传闻讨论"


class IssueType(str, Enum):
    CONTENT_SHORTAGE = "内容不足"
    DESIGN_DISAGREEMENT = "设计分歧"
    NUMERIC_CONTROVERSY = "数值争议"
    TECH_FAULT = "技术故障"
    REWARD_DISPUTE = "奖励争议"
    COMMUNICATION = "沟通问题"
    COMMUNITY_CONFLICT = "社区冲突"
    OTHER = "其他"


class GameName(str, Enum):
    GENSHIN = "genshin"
    WUTHERING_WAVES = "wuthering_waves"


GAME_DISPLAY = {
    GameName.GENSHIN: "原神",
    GameName.WUTHERING_WAVES: "鸣潮",
}


class VideoCategory(str, Enum):
    OFFICIAL = "official"        # 官方物料
    GUIDE = "guide"              # 攻略解析
    REVIEW = "review"            # 体验评价
    FANWORK = "fanwork"          # 二创内容
    CONTROVERSY = "controversy"  # 争议讨论


class AuthorType(str, Enum):
    OFFICIAL = "official"
    UGC = "ugc"


class PostFlag(str, Enum):
    LOTTERY = "lottery"                  # 抽奖
    AD = "ad"                            # 广告
    SPAM = "spam"                        # 刷屏/无意义
    DUPLICATE = "duplicate"              # 重复
    OFF_TOPIC_CANDIDATE = "off_topic_candidate"  # 疑似无关
    OVERLENGTH = "overlength"            # 超长文本


class AnnotatorType(str, Enum):
    """金标准两层策略（2026-08-16 用户确认）：
    strong_model_seed = 强模型种子标注（开发 Agent 生成，第一层）
    human = 人工标注/复核（用户，第二层，逐步升级为人工金标准）
    """
    STRONG_MODEL_SEED = "strong_model_seed"
    HUMAN = "human"


class AnnotateStage(str, Enum):
    CHEAP = "cheap"      # 低成本模型结构化标注
    STRONG = "strong"    # 强模型复核
    HUMAN = "human"      # 人工审核/标注
