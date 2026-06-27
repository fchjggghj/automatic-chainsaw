"""逐关键词串行爬虫 — 每次只跑一个关键词，跑完再跑下一个"""
import sys
import asyncio
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path
from crawler.engine import CrawlerEngine

# 所有关键词
KEYWORDS = [
    '快穿', '无限流', '综影视', '综漫',
    '穿书攻略', '炮灰攻略', '副本攻略', '炮灰逆袭', '炮灰系统',
    '穿越万界', '万界穿行', '位面穿越', '世界穿梭', '诸天流', '穿越诸界',
    '副本通关', '无限副本', '积分兑换',
    '快穿逆袭', '快穿甜宠', '多世界',
    '穿书', '系统文',
]

async def main():
    total_stats = {
        "searched": 0, "filtered": 0, "downloaded": 0,
        "failed": 0, "skipped": 0, "replaced": 0,
    }

    for i, kw in enumerate(KEYWORDS, 1):
        print(f"\n{'#' * 60}")
        print(f"# 关键词 [{i}/{len(KEYWORDS)}]: {kw}")
        print(f"{'#' * 60}")

        engine = CrawlerEngine(
            config_path=Path("config.json"),
            on_log=lambda msg: print(msg, flush=True),
        )

        stats = await engine.run(
            keywords=[kw],
            auto_download=True,
        )

        for k in total_stats:
            total_stats[k] += stats.get(k, 0)

        print(f"\n>>> 关键词 '{kw}' 完成: 搜索{stats['searched']} | 过滤{stats['filtered']} | "
              f"下载{stats['downloaded']} | 失败{stats['failed']} | 跳过{stats['skipped']}")
        print(f">>> 累计: 下载{total_stats['downloaded']} | 失败{total_stats['failed']} | 跳过{total_stats['skipped']}")

    print(f"\n{'=' * 60}")
    print(f"全部完成！总统计: {total_stats}")
    print(f"{'=' * 60}")

asyncio.run(main())
