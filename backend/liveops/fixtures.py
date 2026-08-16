"""固定样本夹具加载：synthetic_100（合成，仅管道验证，绝不冒充真实数据）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import config
from .schema import CommunityPost, ContentItem, StudyConfig


@dataclass
class Fixture:
    name: str
    study: StudyConfig
    posts: list[CommunityPost]
    videos: list[ContentItem]
    seed_annotations: dict[str, dict]

    @property
    def synthetic(self) -> bool:
        return True


def load_fixture(name: str = "synthetic_100") -> Fixture:
    base = config.DATA_DIR / "fixtures" / name
    study = StudyConfig.model_validate(json.loads((base / "study.json").read_text(encoding="utf-8")))
    videos = [ContentItem.model_validate(v) for v in json.loads((base / "videos.json").read_text(encoding="utf-8"))]
    posts = []
    for line in (base / "posts.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            posts.append(CommunityPost.model_validate(json.loads(line)))
    seeds = json.loads((base / "seed_annotations.json").read_text(encoding="utf-8"))
    return Fixture(name=name, study=study, posts=posts, videos=videos, seed_annotations=seeds)
