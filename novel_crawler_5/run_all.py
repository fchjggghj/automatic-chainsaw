"""启动串行爬虫 — 全关键词全站点搜索下载"""
import sys
import asyncio
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path
from crawler.engine import CrawlerEngine

# 精选关键词（去掉太宽泛的"穿书""系统文"等，避免大量无关结果）
KEYWORDS = [
    # 核心词（搜索量大，匹配精准）
    '快穿', '无限流', '综影视', '综漫',
    # 攻略系（精准匹配）
    '穿书攻略', '炮灰攻略', '副本攻略', '炮灰逆袭', '炮灰系统',
    # 穿越系（精准匹配）
    '穿越万界', '万界穿行', '位面穿越', '世界穿梭', '诸天流', '穿越诸界',
    # 副本系
    '副本通关', '无限副本', '积分兑换',
    # 快穿衍生
    '快穿逆袭', '快穿甜宠', '多世界',
]

async def main():
    engine = CrawlerEngine(
        config_path=Path("config.json"),
        on_log=lambda msg: print(msg, flush=True),
    )
    
    print(f"启动串行爬虫: {len(KEYWORDS)} 个关键词 × 13 个处理器")
    print(f"关键词: {KEYWORDS}")
    print()
    
    stats = await engine.run(
        keywords=KEYWORDS,
        auto_download=True,
    )
    
    print(f"\n最终统计: {stats}")

asyncio.run(main())
