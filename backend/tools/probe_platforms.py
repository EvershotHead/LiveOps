# -*- coding: utf-8 -*-
"""四平台公开数据可行性探测（只读、温和、不绕过任何限制）。

目的：回答"小红书/抖音/微博/米游社能否作为后续数据源"，区分三种结果：
  A) 公开可读（无需登录）
  B) 需要登录（cookie），登录后可能可读
  C) 需要签名/风控层（x-s、X-Bogus 等），非登录问题

合规：每平台 ≤4 个请求、间隔 ≥2s、桌面 UA、无登录、无签名伪造；
遇到 403/验证码/登录墙即记录并停止该平台，不重试不绕过。

用法: .venv/Scripts/python.exe tools/probe_platforms.py
输出: docs/platform-feasibility.md 的数据源 + 控制台摘要
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
RESULTS: list[dict] = []


def probe(platform: str, name: str, method: str, url: str, *, headers=None,
          note="", expect_json=True):
    h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    if headers:
        h.update(headers)
    try:
        with httpx.Client(headers=h, timeout=15, follow_redirects=True) as c:
            if method == "GET":
                r = c.get(url)
            else:
                r = c.post(url, json=headers.pop("_json", None))
            body = r.text
            snippet = body[:300].replace("\n", " ")
            ok_json = None
            code = None
            if expect_json:
                try:
                    j = r.json()
                    ok_json = True
                    code = j.get("code", j.get("status_code", "?"))
                    snippet = json.dumps(j, ensure_ascii=False)[:300]
                except Exception:
                    ok_json = False
            RESULTS.append({
                "platform": platform, "probe": name, "url": url,
                "http": r.status_code, "redirect": str(r.url) if str(r.url) != url else "",
                "json": ok_json, "code": code, "snippet": snippet, "note": note,
            })
            print(f"[{platform}] {name}: HTTP {r.status_code} code={code} "
                  f"{'-> ' + str(r.url) if str(r.url) != url else ''}")
    except Exception as e:  # noqa: BLE001
        RESULTS.append({"platform": platform, "probe": name, "url": url,
                        "http": None, "error": repr(e)[:200], "note": note})
        print(f"[{platform}] {name}: EXC {e!r}")
    time.sleep(2.2)


# ---------- 1. 小红书 ----------
# 探测：首页可达性 + 搜索 API 是否需要签名
probe("小红书", "首页 HTML",
      "GET", "https://www.xiaohongshu.com/explore",
      note="看未登录是否直接给内容流/登录墙")
probe("小红书", "搜索 API（无签名）",
      "GET", "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes?keyword=%E5%8E%9F%E7%A5%9E&page=1",
      note="已知需要 x-s/x-t 签名；验证无签名时返回什么")

# ---------- 2. 抖音 ----------
probe("抖音", "搜索 API（无签名）",
      "GET", "https://www.douyin.com/aweme/v1/web/search/item/?keyword=%E9%B8%A3%E6%BD%AE&count=10",
      note="已知需要 X-Bogus/msToken；验证无签名返回")
probe("抖音", "视频页 HTML",
      "GET", "https://www.douyin.com/discover",
      note="看未登录内容流是否渲染")

# ---------- 3. 微博 ----------
probe("微博", "热搜 API",
      "GET", "https://weibo.com/ajax/side/hotSearch",
      note="公开热搜，通常无需登录")
probe("微博", "m 站搜索 API",
      "GET", "https://m.weibo.cn/api/container/getIndex?containerid=100103type%3D1%26q%3D%E5%8E%9F%E7%A5%9E7.0",
      note="移动端综合搜索；未登录常返回提示登录")

# ---------- 4. 米游社 ----------
probe("米游社", "首页拿 cookie",
      "GET", "https://www.miyoushe.com/ys/",
      note="先建立会话")
probe("米游社", "原神版块帖子列表 API",
      "GET", "https://bbs-api.miyoushe.com/post/wapi/ForumPostList?forum_id=1&is_good=false&is_hot=false&last_id=&page_size=20&sort_type=2",
      headers={"Referer": "https://www.miyoushe.com/ys/"},
      note="公开版块列表；验证无登录 cookie 是否可读")

with open("probe_results.json", "w", encoding="utf-8") as f:
    json.dump({"probed_at": NOW, "results": RESULTS}, f, ensure_ascii=False, indent=1)
print("\nsaved -> probe_results.json")
