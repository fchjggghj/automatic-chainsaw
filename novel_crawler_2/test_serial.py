"""测试串行搜索下载流程 — 只跑1个关键词1个站点"""
import sys
import asyncio
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path
from crawler.engine import CrawlerEngine

async def main():
    engine = CrawlerEngine(config_path=Path("config.json"))
    
    # 用1个关键词、指定1个站点，自动下载
    print("=== 串行搜索下载测试 ===")
    stats = await engine.run(
        keywords=["快穿"],
        auto_download=True,
        site_names=["爱下电子书"],  # 只测试爱下电子书
    )
    
    print(f"\n统计: {stats}")
    
    # 查看任务详情
    results = engine.get_results()
    print(f"\n任务数: {len(results)}")
    for r in results[:10]:
        print(f"  [{r['status']}] {r['title'][:40]} from={r['source']} "
              f"dedup={r['dedup_action']} retries={r['retry_count']}")
    
    # 查看进度
    progress = engine.get_progress()
    print(f"\n进度: {progress['tasks']}")
    print(f"当前: keyword={progress['current_keyword']} site={progress['current_site']}")

asyncio.run(main())
