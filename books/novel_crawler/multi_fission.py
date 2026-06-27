#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多目标裂变式快穿小说下载器
所有搜索关键词必须包含快穿/无限流/综影视/综漫/诸天流/穿书等核心主题词
"""

import os
import sys
import time
import json
import random
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Set, Dict

# ========== 配置 ==========
API_ENDPOINTS = [
    "http://127.0.0.1:8765",
    "http://127.0.0.1:8766",
    "http://127.0.0.1:8767",
    "http://127.0.0.1:8768",
    "http://127.0.0.1:8769",
]

DOWNLOAD_DIR = Path("C:/Users/Administrator/Desktop/books/books/novel_crawler/downloads")
HISTORY_FILE = Path(__file__).parent / "multi_fission_history.json"

# ========== 核心主题词（必须包含至少一个） ==========
CORE_THEMES = [
    "快穿", "无限流", "综影视", "综漫", "诸天流",
    "穿书", "快穿之", "快穿：", "快穿: ",
    "[快穿]", "【快穿】", "（快穿）", "#快穿#",
    "无限流之", "[无限流]", "【无限流】",
    "综武侠", "综英美", "综同人",
    "炮灰逆袭", "女配逆袭", "系统快穿",
]

# ========== 种子关键词（全部经过验证，与快穿强相关） ==========
SEED_KEYWORDS = [
    # 基础主题
    "快穿", "快穿之", "快穿：", "快穿系统", "快穿文", "快穿小说",
    "无限流", "无限流之", "综影视", "综漫", "诸天流", "穿书",
    # 情感类型
    "快穿甜宠", "快穿爽文", "快穿逆袭", "快穿打脸", "快穿虐渣",
    "快穿苏爽", "快穿沙雕", "快穿搞笑", "快穿轻松", "快穿小甜饼",
    "快穿治愈", "快穿救赎", "快穿HE",
    # 主角设定
    "快穿无CP", "快穿1v1", "快穿双男主", "快穿万人迷", "快穿女强",
    "快穿强强", "快穿病娇", "快穿黑化",
    # 身份/角色
    "快穿炮灰", "快穿女配", "快穿反派", "快穿主角", "快穿宿主",
    "快穿任务者", "快穿玩家",
    # 题材/世界
    "快穿娱乐圈", "快穿年代", "快穿末世", "快穿星际", "快穿古代",
    "快穿现代", "快穿民国", "快穿武侠", "快穿仙侠", "快修真",
    "快穿宫斗", "快穿宅斗", "快穿种田", "快穿美食", "快穿萌宠",
    "快穿兽世", "快穿ABO", "快穿网游", "快穿电竞", "快穿校园",
    "快穿职场", "快穿悬疑", "快穿恐怖", "快穿灵异", "快穿科幻",
    "快穿机甲", "快穿丧尸",
    # 职业/身份
    "快穿将军", "快穿王爷", "快穿农家", "快穿神医", "快穿锦衣卫",
    "快穿皇帝", "快穿公主", "快穿皇后", "快穿贵妃",
    # 综影视综漫
    "综影视快穿", "综漫快穿", "快穿综影视", "快穿综漫",
    "快穿漫威", "快穿DC", "快穿复联", "快穿哈利波特",
    "快穿火影", "快穿海贼", "快穿死神", "快穿柯南",
    "快穿鬼灭之刃", "快穿咒术回战", "快穿进击的巨人",
    "快穿甄嬛传", "快穿延禧攻略", "快穿还珠格格", "快穿三生三世",
    "快穿陈情令", "快穿琅琊榜", "快穿知否", "快穿庆余年",
    "快穿开端", "快穿狂飙", "快穿流浪地球", "快穿三体",
    # 无限流细分
    "无限流恐怖", "无限流副本", "无限流游戏", "无限流逃生",
    "无限流解谜", "无限流悬疑", "无限流推理",
    # 其他类型
    "快穿直播", "快穿金手指", "快穿养崽", "快穿追妻火葬场",
    "快穿攻略", "快穿任务", "快穿位面", "快穿世界",
    "快穿古言", "快穿现言", "快穿奇幻", "快穿动漫",
    "快穿二次元", "快穿影视", "快穿电影", "快穿电视剧",
    "快穿唐朝", "快穿宋朝", "快穿明朝", "快穿清朝",
]

# ========== 修饰词（用于与核心主题组合裂变） ==========
MODIFIERS = [
    "甜宠", "爽文", "逆袭", "打脸", "虐渣", "攻略", "系统",
    "无CP", "1v1", "双男主", "女配", "炮灰", "病娇", "黑化",
    "养崽", "娱乐圈", "年代", "末世", "星际", "沙雕",
    "直播", "金手指", "万人迷", "女强", "强强", "轻松", "搞笑",
    "古言", "现言", "民国", "武侠", "仙侠", "宫斗", "宅斗", "种田",
    "美食", "萌宠", "兽世", "校园", "职场", "悬疑", "恐怖",
    "灵异", "科幻", "机甲", "古代", "清朝", "将军", "王爷",
    "农家", "神医", "锦衣卫", "动漫", "二次元", "影视", "电影",
    "电视剧", "漫威", "DC", "哈利波特", "甄嬛传", "三生三世",
    "陈情令", "琅琊榜", "知否", "庆余年", "火影", "海贼", "死神",
    "柯南", "鬼灭之刃", "咒术回战", "救赎", "治愈", "小甜饼",
    "追妻火葬场", "反派", "宿主", "任务", "位面", "世界",
    "游戏", "副本", "逃生", "解谜", "推理",
]

# ========== 世界类型 ==========
WORLDS = [
    "古代", "现代", "末世", "星际", "修真", "仙侠", "武侠", "民国",
    "清朝", "唐朝", "宋朝", "明朝", "宫廷", "后宫", "宅斗", "宫斗",
    "江湖", "校园", "职场", "娱乐圈", "电竞", "网游", "种田",
    "兽世", "ABO", "西幻", "魔法", "机甲", "丧尸", "恐怖", "灵异",
    "童话", "悬疑", "推理", "年代", "七零", "八零", "九零",
    "三国", "水浒", "西游", "红楼", "封神", "洪荒", "聊斋",
]

# ========== 综影视/综漫作品 ==========
SHOWS = [
    "甄嬛传", "延禧攻略", "还珠格格", "三生三世", "陈情令",
    "琅琊榜", "知否", "庆余年", "开端", "狂飙", "流浪地球",
    "火影", "海贼", "死神", "柯南", "进击的巨人",
    "鬼灭之刃", "咒术回战", "漫威", "DC", "复联", "哈利波特",
    "红楼梦", "西游记", "水浒传", "三国演义", "封神榜",
    "倚天屠龙记", "神雕侠侣", "射雕英雄传", "天龙八部",
    "鹿鼎记", "笑傲江湖", "绝代双骄", "小鱼儿与花无缺",
    "仙剑奇侠传", "步步惊心", "宫锁心玉", "陆贞传奇",
    "花千骨", "楚乔传", "香蜜沉沉",
    "山河令", "琉璃", "苍兰诀", "星汉灿烂",
]

# 核心前缀（用于生成裂变）
CORE_PREFIXES = [
    "快穿", "快穿之", "快穿：",
    "无限流", "无限流之",
    "综影视", "综", "综漫",
    "穿书", "穿书之",
    "诸天", "诸天流",
    "炮灰", "炮灰之",
    "女配", "女配之",
]


def is_kuaichuan_related(keyword: str) -> bool:
    """检查关键词是否与快穿/无限流/综影视等核心主题相关"""
    for theme in CORE_THEMES:
        if theme in keyword:
            return True
    return False


class MultiFissionCrawler:
    def __init__(self):
        self.keyword_pool: Set[str] = set()
        self.searched_keywords: Set[str] = set()
        self.last_new_download_time: datetime = datetime.now()
        self.total_downloaded: int = 0
        self.round_count: int = 0
        self.load_history()
        self.init_keyword_pool()

    def init_keyword_pool(self):
        """初始化关键词池，只保留快穿相关的"""
        count = 0
        for kw in SEED_KEYWORDS:
            if is_kuaichuan_related(kw):
                self.keyword_pool.add(kw)
                count += 1
        print(f"[初始化] 种子关键词: {count} 个")

    def load_history(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.searched_keywords = set(data.get('searched', []))
                    self.last_new_download_time = datetime.fromisoformat(
                        data.get('last_new', datetime.now().isoformat())
                    )
                    self.total_downloaded = data.get('total', 0)
                print(f"[历史] 已加载 {len(self.searched_keywords)} 个搜索历史")
            except Exception as e:
                print(f"[历史] 加载失败: {e}")

    def save_history(self):
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'searched': list(self.searched_keywords),
                    'last_new': self.last_new_download_time.isoformat(),
                    'total': self.total_downloaded,
                    'updated': datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[历史] 保存失败: {e}")

    def generate_fission_keywords(self) -> Set[str]:
        """裂变生成新关键词，全部必须包含核心主题词"""
        new_keywords: Set[str] = set()

        # 1. 快穿 + 修饰词
        for mod in MODIFIERS:
            new_keywords.add(f"快穿{mod}")
            new_keywords.add(f"快穿之{mod}")
            new_keywords.add(f"[快穿]{mod}")
            new_keywords.add(f"【快穿】{mod}")
            new_keywords.add(f"（快穿）{mod}")

        # 2. 快穿 + 世界
        for world in WORLDS:
            new_keywords.add(f"快穿{world}")
            new_keywords.add(f"快穿之{world}")
            new_keywords.add(f"快穿：{world}")

        # 3. 无限流 + 修饰词
        for mod in MODIFIERS:
            new_keywords.add(f"无限流{mod}")
            new_keywords.add(f"无限流之{mod}")
            new_keywords.add(f"[无限流]{mod}")

        # 4. 综影视/综漫 + 作品名
        for prefix in ["综影视", "综漫", "综", "快穿", "穿书"]:
            for show in SHOWS:
                new_keywords.add(f"{prefix}{show}")
                new_keywords.add(f"{prefix}：{show}")
                new_keywords.add(f"{prefix}之{show}")

        # 5. 穿书 + 修饰词
        for mod in MODIFIERS:
            new_keywords.add(f"穿书{mod}")
            new_keywords.add(f"穿书之{mod}")

        # 6. 诸天流 + 修饰词
        for mod in MODIFIERS:
            new_keywords.add(f"诸天{mod}")
            new_keywords.add(f"诸天流{mod}")
            new_keywords.add(f"诸天：{mod}")

        # 严格过滤：只保留包含核心主题词的
        filtered = {
            kw for kw in new_keywords
            if 2 <= len(kw) <= 25
            and kw not in self.searched_keywords
            and not kw.isdigit()
            and is_kuaichuan_related(kw)
        }
        return filtered

    def get_api_status(self, endpoint: str) -> Dict:
        try:
            r = requests.get(f"{endpoint}/api/progress", timeout=5)
            return r.json()
        except:
            return {'running': False}

    def start_download(self, endpoint: str, keywords: List[str]) -> bool:
        try:
            data = {'keywords': keywords, 'site_names': None, 'auto_download': True}
            headers = {'Content-Type': 'application/json; charset=utf-8'}
            r = requests.post(
                f"{endpoint}/api/run",
                data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
                headers=headers,
                timeout=5
            )
            return r.json().get('ok', False)
        except:
            return False

    def find_idle_endpoint(self) -> str:
        for endpoint in API_ENDPOINTS:
            status = self.get_api_status(endpoint)
            if not status.get('running', False):
                return endpoint
        return ""

    def get_all_status(self) -> Dict[str, Dict]:
        result = {}
        for ep in API_ENDPOINTS:
            result[ep] = self.get_api_status(ep)
        return result

    def run(self):
        print("=" * 70)
        print("多目标裂变式快穿小说下载器 (精准版)")
        print(f"并行实例: {len(API_ENDPOINTS)} 个")
        print(f"端点: {API_ENDPOINTS}")
        print("=" * 70)
        print(f"关键词池: {len(self.keyword_pool)} 个")
        print(f"已搜索: {len(self.searched_keywords)} 个")
        print(f"核心主题词: {len(CORE_THEMES)} 个")
        print("=" * 70)

        while True:
            self.round_count += 1
            print(f"\n{'=' * 70}")
            print(f"第 {self.round_count} 轮裂变搜索")
            print(f"{'=' * 70}")

            elapsed = (datetime.now() - self.last_new_download_time).total_seconds() / 3600
            if elapsed >= 24:
                print(f"[停止] 已连续 {elapsed:.1f} 小时无新下载")
                break
            print(f"[检查] 距上次新下载 {elapsed:.1f} 小时")

            fission = self.generate_fission_keywords()
            self.keyword_pool.update(fission)
            candidates = [kw for kw in self.keyword_pool if kw not in self.searched_keywords]

            if not candidates:
                print("[警告] 无新关键词，强制裂变...")
                extra = self.generate_fission_keywords()
                candidates = list(extra)
                if not candidates:
                    print("[停止] 无法生成更多关键词")
                    break

            random.shuffle(candidates)
            candidates.sort(key=lambda x: (len(x), x))

            print(f"[候选] 本轮搜索关键词: {min(50, len(candidates))} 个")

            batch_size = 10

            for i in range(0, min(50, len(candidates)), batch_size):
                batch = candidates[i:i + batch_size]

                while True:
                    ep = self.find_idle_endpoint()
                    if ep:
                        break
                    print("[等待] 所有端点忙碌，等待30秒...")
                    time.sleep(30)

                print(f"[分发] {ep} -> {batch}")
                if self.start_download(ep, batch):
                    for kw in batch:
                        self.searched_keywords.add(kw)
                else:
                    print(f"[错误] 启动失败: {ep}")

                time.sleep(2)

            print("[等待] 等待本轮所有端点完成...")
            while True:
                time.sleep(15)
                all_idle = all(
                    not self.get_api_status(ep).get('running', False)
                    for ep in API_ENDPOINTS
                )
                if all_idle:
                    break
                statuses = self.get_all_status()
                total_dl = sum(s.get('stats', {}).get('downloaded', 0) for s in statuses.values())
                running = sum(1 for s in statuses.values() if s.get('running', False))
                print(f"[进度] 总下载: {total_dl} | 运行中: {running}/5 | 轮次: {self.round_count}")

            statuses = self.get_all_status()
            round_dl = sum(s.get('stats', {}).get('downloaded', 0) for s in statuses.values())
            new_count = round_dl - self.total_downloaded
            self.total_downloaded = round_dl

            if new_count > 0:
                self.last_new_download_time = datetime.now()
                print(f"[成功] 本轮新增 {new_count} 本，总下载 {self.total_downloaded}")
            else:
                print(f"[结果] 本轮无新下载，总下载 {self.total_downloaded}")

            self.save_history()

            rest = random.randint(5, 15)
            print(f"[休息] {rest} 秒后继续...")
            time.sleep(rest)

        print("\n" + "=" * 70)
        print("多目标裂变下载器已停止")
        print(f"总轮次: {self.round_count}")
        print(f"总下载: {self.total_downloaded}")
        print("=" * 70)
        self.save_history()


if __name__ == '__main__':
    crawler = MultiFissionCrawler()
    try:
        crawler.run()
    except KeyboardInterrupt:
        print("\n[中断] 用户手动停止")
        crawler.save_history()
    except Exception as e:
        print(f"\n[错误] {e}")
        crawler.save_history()
        raise
