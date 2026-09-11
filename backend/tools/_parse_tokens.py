# -*- coding: utf-8 -*-
"""标注 token 串解析器（开发 Agent 内部工具）。

用法: python tools/_parse_tokens.py <ids_file> <tokens_file> <out_json>
ids_file: emit 输出（seq|post_id|text 行）
tokens_file: 逗号分隔标注 token，100 个，顺序对应
token 语法: 主题1+主题2|立场|情绪|强度|意图|置信|问题性质(可选)
特殊: 0=单字弃权 l=楼中楼弃权 g=梗弃权 k=跨游戏弃权 x[置信]=无关
"""
import json
import sys

TOPIC = {"js": "角色设计与美术", "zd": "战斗与玩法", "jq": "剧情与世界观", "dt": "地图与探索",
         "bb": "版本内容量", "hd": "活动设计", "yh": "养成与资源", "ck": "抽卡与商业化",
         "ph": "平衡与强度", "xn": "性能与缺陷", "jk": "界面与便利性", "gc": "官方沟通与社区生态"}
ST = {"c": "支持", "f": "反对", "z": "中立", "h": "混合"}
EM = {"xy": "喜悦", "qw": "期待", "jy": "惊讶", "sw": "失望", "fn": "愤怒",
      "lv": "焦虑", "tw": "调侃玩梗", "wu": "无明显情绪"}
IN = {"cz": "称赞", "ts": "体验陈述", "wt": "提问", "bg": "问题报告",
      "j2": "改进建议", "wg": "玩梗", "cy": "冲突回应", "cs": "传闻讨论"}


def parse(tok):
    if "|" not in tok:
        if tok == "0": return {"r": None, "a": "单字语境不足", "c": 0.17}
        if tok == "l": return {"r": None, "a": "楼中楼梗语境不足", "c": 0.28}
        if tok == "g": return {"r": None, "a": "梗语境不足", "c": 0.3}
        if tok == "k": return {"r": None, "a": "跨游戏梗语境不足", "c": 0.4}
        if tok.startswith("x"): return {"r": False, "c": float(tok[1:] or 0.55)}
        raise ValueError(tok)
    p = tok.split("|")
    d = {"r": True, "t": [TOPIC[x] for x in p[0].split("+")], "s": ST[p[1]],
         "e": EM[p[2]], "i": int(p[3]), "n": IN[p[4]], "c": float(p[5])}
    if len(p) > 6 and p[6]:
        if p[6] in ("无", "可能", "明显"):  # 反讽槽位
            d["y"] = p[6]
        else:
            d["q"] = p[6]
    return d


def main():
    ids = []
    for line in open(sys.argv[1], encoding="utf-8"):
        m = __import__("re").match(r"^(\d+)\|(\d+)\|", line)
        if m:
            ids.append((int(m.group(1)), m.group(2)))
    ids.sort()
    toks = [t.strip() for t in open(sys.argv[2], encoding="utf-8").read().replace("\n", " ").split(",")]
    toks = [t for t in toks if t]
    assert [s for s, _ in ids] == list(range(1, len(toks) + 1)), f"seq mismatch ids={len(ids)} toks={len(toks)}"
    A = [parse(t) for t in toks]
    out = [{"id": pid, **a} for (_, pid), a in zip(ids, A)]
    json.dump(out, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("written", len(out))


if __name__ == "__main__":
    main()
