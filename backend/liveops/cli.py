"""命令行入口。

用法：
  uv run liveops run --fixture synthetic_100     # 合成夹具端到端（ScriptedLLM 回放种子标注）
  uv run liveops run --fixture synthetic_100 --real   # 有密钥时用真实 LLM 跑同一夹具并对照
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .fixtures import load_fixture
from .harness.graph import HarnessDeps, run_pipeline
from .llm import MockLLM, ResponseCache, ScriptedLLM, get_client, register_scripted
from .llm.prompts import v1


def cmd_run(args: argparse.Namespace) -> int:
    fx = load_fixture(args.fixture)
    cache = ResponseCache(config.RUNS_DIR / "llm-cache.sqlite")
    if args.real:
        llm = get_client(cache)
        if isinstance(llm, MockLLM):
            print("错误：未配置 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL，无法使用 --real", file=sys.stderr)
            return 2
        strong = llm
    else:
        register_scripted(v1.ANNOTATE_VERSION, fx.seed_annotations)
        llm = ScriptedLLM(cache=cache)
        strong = llm

    print(f"[run] study={fx.study.study_id} posts={len(fx.posts)} videos={len(fx.videos)} "
          f"llm={llm.name} fixture_synthetic=true")
    result = run_pipeline(fx.study, fx.posts, fx.videos, HarnessDeps(llm, strong),
                          runs_dir=config.RUNS_DIR)
    run = result.run
    print(f"[done] run_id={run.run_id} status={run.status.value} 耗时={run.duration_s:.1f}s")
    print(f"[metrics] 有效相关评论={result.state['metrics']['dataset']['relevant_posts']} "
          f"弃权={result.state['metrics']['dataset']['abstain_count']}")
    print(f"[verify] 结论验证={'通过' if result.state['verify_result']['passed'] else '未通过'} "
          f"结论数={len(result.state.get('claims', []))}")
    report = Path(config.RUNS_DIR) / run.run_id / "report.html"
    print(f"[report] {report}")
    return 0 if run.status.value == "completed" else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="liveops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="运行分析任务")
    run_p.add_argument("--fixture", default="synthetic_100")
    run_p.add_argument("--real", action="store_true", help="使用真实 LLM（需配置密钥）")
    run_p.set_defaults(func=cmd_run)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
