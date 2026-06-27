#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
裂变式快穿小说下载器
功能：
1. 基于已有关键词裂变生成新关键词
2. 从已下载小说书名中提取关键词
3. 24小时持续循环搜索
4. 当24小时内无新下载时自动停止
"""

import os
import sys
import time
import json
import random
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Set, Dict

# ========== 配置 ==========
API_BASE = "http://127.0.0.1:8765"
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
CONFIG_PATH = Path(__file__).parent / "config.json"
HISTORY_FILE = Path(__file__).parent / "fission_history.json"

# 核心种子关键词（永不删除）
SEED_KEYWORDS = [
    "快穿", "无限流", "综影视", "综漫", "诸天流", "副本攻略",
    "炮灰逆袭", "炮灰攻略", "穿书攻略", "系统文", "穿越万界",
    "位面穿越", "多世界", "无限副本", "世界任务", "积分兑换",
    "世界穿梭", "万界穿行", "穿书", "快穿甜宠", "快穿逆袭",
    "快穿HE", "快穿系统", "快穿爽文", "快穿无CP", "快穿1v1",
    "快穿双男主", "快穿炮灰", "快穿女配", "快穿攻略", "快穿病娇",
    "快穿黑化", "快穿养崽", "快穿娱乐圈", "快穿年代", "快穿末世",
    "快穿星际", "快穿无限流", "快穿打脸", "快穿苏爽", "快穿救赎",
    "快穿治愈", "快穿沙雕", "快穿直播", "快穿金手指", "快穿万人迷",
    "快穿追妻火葬场", "快穿虐渣", "快穿女强", "快穿强强", "快穿小甜饼",
    "快穿轻松", "快穿搞笑", "快穿奇幻", "快穿古言", "快穿现言",
    "快穿民国", "快穿武侠", "快穿宫斗", "快穿宅斗", "快穿种田",
    "快穿美食", "快穿萌宠", "快穿兽世", "快穿ABO", "快穿网游",
    "快穿电竞", "快穿校园", "快穿职场", "快穿悬疑", "快穿恐怖",
    "快穿灵异", "快穿科幻", "快穿机甲", "快穿古代", "快穿唐朝",
    "快穿宋朝", "快穿明朝", "快穿清朝", "快穿将军", "快穿王爷",
    "快穿农家", "快穿神医", "快穿锦衣卫", "快穿动漫", "快穿二次元",
    "快穿影视", "快穿电影", "快穿电视剧", "快穿复联", "快穿漫威",
    "快穿DC", "快穿哈利波特", "快穿三体", "快穿甄嬛传", "快穿延禧攻略",
    "快穿还珠格格", "快穿三生三世", "快穿陈情令", "快穿琅琊榜",
    "快穿知否", "快穿庆余年", "快穿开端", "快穿狂飙", "快穿流浪地球",
    "快穿火影", "快穿海贼", "快穿死神", "快穿柯南", "快穿进击的巨人",
    "快穿鬼灭之刃", "快穿咒术回战",
]

# 前缀/后缀裂变模板
PREFIXES = ["", "【", "[", "（", "#", "「"]
SUFFIXES = ["", "】", "]", "）", "#", "」", "之", "：", " "]
MODIFIERS = [
    "甜宠", "爽文", "逆袭", "打脸", "虐渣", "攻略", "系统",
    "无CP", "1v1", "双男主", "女配", "炮灰", "病娇", "黑化",
    "养崽", "娱乐圈", "年代", "末世", "星际", "无限流", "沙雕",
    "直播", "金手指", "万人迷", "女强", "强强", "轻松", "搞笑",
    "古言", "现言", "民国", "武侠", "宫斗", "宅斗", "种田",
    "美食", "萌宠", "兽世", "校园", "职场", "悬疑", "恐怖",
    "灵异", "科幻", "机甲", "古代", "清朝", "将军", "王爷",
    "农家", "神医", "锦衣卫", "动漫", "二次元", "影视", "电影",
    "电视剧", "漫威", "DC", "哈利波特", "甄嬛传", "三生三世",
    "陈情令", "琅琊榜", "知否", "庆余年", "火影", "海贼", "死神",
    "柯南", "鬼灭之刃", "咒术回战",
]

WORLDS = [
    "古代", "现代", "末世", "星际", "修真", "仙侠", "武侠", "民国",
    "清朝", "唐朝", "宋朝", "明朝", "宫廷", "后宫", "宅斗", "宫斗",
    "江湖", "校园", "职场", "娱乐圈", "电竞", "网游", "种田",
    "兽世", "ABO", "西幻", "魔法", "机甲", "丧尸", "恐怖", "灵异",
    "童话", "悬疑", "推理", "年代", "七零", "八零", "九零", "零零",
    "三国", "水浒", "西游", "红楼", "封神", "洪荒", "聊斋",
]


class FissionCrawler:
    def __init__(self):
        self.keyword_pool: Set[str] = set(SEED_KEYWORDS)
        self.searched_keywords: Set[str] = set()
        self.last_new_download_time: datetime = datetime.now()
        self.total_downloaded: int = 0
        self.round_count: int = 0
        self.load_history()
        self.load_config_keywords()

    def load_history(self):
        """加载搜索历史"""
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
        """保存搜索历史"""
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

    def load_config_keywords(self):
        """从config.json加载关键词"""
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    kw_list = cfg.get('search', {}).get('keywords', [])
                    self.keyword_pool.update(kw_list)
                    print(f"[配置] 从config.json加载 {len(kw_list)} 个关键词")
            except Exception as e:
                print(f"[配置] 加载失败: {e}")

    def extract_from_filenames(self) -> Set[str]:
        """从已下载小说文件名中提取关键词"""
        new_keywords: Set[str] = set()
        if not DOWNLOAD_DIR.exists():
            return new_keywords

        for root, _, files in os.walk(DOWNLOAD_DIR):
            for fname in files:
                if not fname.endswith('.txt'):
                    continue
                # 去掉.txt后缀和_dup_标记
                name = fname.replace('.txt', '')
                name = name.split('_dup_')[0]

                # 提取书名中的关键词片段
                # 去掉常见前缀
                for prefix in ['快穿\\', '综影视', '综漫', '之', '：', ':', ' ']:
                    if name.startswith(prefix):
                        name = name[len(prefix):]

                # 分割提取关键片段
                parts = re.split(r'[：:之\\/\[\]【】（）(),，.。!！?？""''《》]', name)
                for part in parts:
                    part = part.strip()
                    if 2 <= len(part) <= 15 and not part.isdigit():
                        # 只保留看起来是中文词汇的
                        if any('\u4e00' <= c <= '\u9fff' for c in part):
                            new_keywords.add(part)

                # 提取包含"快穿"的完整短语
                if '快穿' in name:
                    # 提取"快穿XXX"模式
                    match = re.search(r'快穿[：:]?(.{2,10})', name)
                    if match:
                        new_keywords.add(f"快穿{match.group(1)}")

                # 提取"综影视"后的内容
                if '综影视' in name:
                    match = re.search(r'综影视[：:]?(.{2,10})', name)
                    if match:
                        new_keywords.add(f"综影视{match.group(1)}")

        print(f"[提取] 从文件名提取 {len(new_keywords)} 个新关键词")
        return new_keywords

    def generate_fission_keywords(self) -> Set[str]:
        """裂变生成新关键词"""
        new_keywords: Set[str] = set()
        base_kws = [k for k in self.keyword_pool if '快穿' in k or '无限流' in k or '综' in k]

        # 1. 组合裂变：快穿 + 世界
        for base in base_kws:
            for world in WORLDS:
                new_keywords.add(f"{base}{world}")
                new_keywords.add(f"{base}之{world}")
                new_keywords.add(f"{base}：{world}")

        # 2. 组合裂变：快穿 + 修饰词
        for mod in MODIFIERS:
            new_keywords.add(f"快穿{mod}")
            new_keywords.add(f"快穿之{mod}")
            new_keywords.add(f"[快穿]{mod}")
            new_keywords.add(f"【快穿】{mod}")
            new_keywords.add(f"（快穿）{mod}")
            new_keywords.add(f"#快穿#{mod}")
            new_keywords.add(f"快穿：{mod}")
            new_keywords.add(f"快穿 {mod}")

        # 3. 无限流 + 修饰词
        for mod in MODIFIERS:
            new_keywords.add(f"无限流{mod}")
            new_keywords.add(f"无限流之{mod}")
            new_keywords.add(f"[无限流]{mod}")
            new_keywords.add(f"无限流：{mod}")

        # 4. 前缀后缀变体
        for kw in list(self.keyword_pool):
            for pre in PREFIXES:
                for suf in SUFFIXES:
                    if pre or suf:
                        new_keywords.add(f"{pre}{kw}{suf}")

        # 5. 双关键词组合
        pool_list = list(self.keyword_pool)
        for i in range(min(50, len(pool_list))):
            for j in range(i + 1, min(50, len(pool_list))):
                if pool_list[i] != pool_list[j]:
                    new_keywords.add(f"{pool_list[i]}{pool_list[j]}")
                    new_keywords.add(f"{pool_list[i]}之{pool_list[j]}")

        # 6. 综影视/综漫 + 具体作品名
        shows = [
            "甄嬛传", "延禧攻略", "还珠格格", "三生三世", "陈情令",
            "琅琊榜", "知否", "庆余年", "开端", "狂飙", "流浪地球",
            "火影", "海贼", "死神", "柯南", "进击的巨人",
            "鬼灭之刃", "咒术回战", "漫威", "DC", "哈利波特",
            "红楼梦", "西游记", "水浒传", "三国演义", "封神榜",
            "倚天屠龙记", "神雕侠侣", "射雕英雄传", "天龙八部",
            "鹿鼎记", "笑傲江湖", "绝代双骄", "小鱼儿与花无缺",
            "仙剑奇侠传", "步步惊心", "宫锁心玉", "陆贞传奇",
            "花千骨", "楚乔传", "三生三世十里桃花", "香蜜沉沉",
            "陈情令", "山河令", "琉璃", "苍兰诀", "星汉灿烂",
        ]
        for prefix in ["综影视", "综", "快穿", "穿书", "穿越"]:
            for show in shows:
                new_keywords.add(f"{prefix}{show}")
                new_keywords.add(f"{prefix}：{show}")
                new_keywords.add(f"{prefix}之{show}")

        # 7. 书名词裂变（短词优先）
        for kw in list(self.keyword_pool):
            if len(kw) > 6:
                # 尝试拆分
                for i in range(2, len(kw) - 1):
                    new_keywords.add(kw[:i])
                    new_keywords.add(kw[i:])

        # 过滤：只保留2-20字符、未被搜索过的
        filtered = {
            kw for kw in new_keywords
            if 2 <= len(kw) <= 20
            and kw not in self.searched_keywords
            and not kw.isdigit()
            and any('\u4e00' <= c <= '\u9fff' for c in kw)
        }

        print(f"[裂变] 生成 {len(filtered)} 个新关键词")
        return filtered

    def get_api_status(self) -> Dict:
        """获取爬虫状态"""
        try:
            r = requests.get(f"{API_BASE}/api/progress", timeout=10)
            return r.json()
        except Exception as e:
            print(f"[API] 获取状态失败: {e}")
            return {'running': False}

    def start_download(self, keywords: List[str]) -> bool:
        """启动下载"""
        try:
            data = {
                'keywords': keywords,
                'site_names': None,
                'auto_download': True
            }
            headers = {'Content-Type': 'application/json; charset=utf-8'}
            r = requests.post(
                f"{API_BASE}/api/run",
                data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
                headers=headers,
                timeout=10
            )
            result = r.json()
            if result.get('ok'):
                print(f"[API] 成功启动 {len(keywords)} 个关键词搜索")
                return True
            else:
                print(f"[API] 启动失败: {result}")
                return False
        except Exception as e:
            print(f"[API] 请求失败: {e}")
            return False

    def wait_for_complete(self, timeout_minutes: int = 30) -> int:
        """等待当前下载完成，返回新增下载数"""
        start_time = time.time()
        last_downloaded = -1
        stable_count = 0
        new_count = 0

        while True:
            time.sleep(10)
            status = self.get_api_status()

            if not status.get('running', False):
                # 检查是否完成了
                stats = status.get('stats', {})
                current = stats.get('downloaded', 0)
                if last_downloaded < 0:
                    last_downloaded = current
                new_count = current - last_downloaded
                print(f"[等待] 下载完成，新增 {new_count} 本")
                break

            stats = status.get('stats', {})
            current = stats.get('downloaded', 0)

            if last_downloaded < 0:
                last_downloaded = current

            elapsed = time.time() - start_time
            if elapsed > timeout_minutes * 60:
                print(f"[等待] 超时 ({timeout_minutes}分钟)，强制结束")
                # 尝试停止
                try:
                    requests.post(f"{API_BASE}/api/stop", timeout=5)
                except:
                    pass
                new_count = current - last_downloaded
                break

            # 显示进度
            if int(elapsed) % 60 == 0:
                print(f"[进度] 运行 {int(elapsed / 60)} 分钟 | "
                      f"搜索 {stats.get('searched', 0)} | "
                      f"已下载 {current}")

        return new_count

    def should_stop(self) -> bool:
        """检查是否应该停止（24小时无新下载）"""
        elapsed = datetime.now() - self.last_new_download_time
        hours = elapsed.total_seconds() / 3600
        if hours >= 24:
            print(f"[停止] 已连续 {hours:.1f} 小时无新下载，停止运行")
            return True
        print(f"[检查] 距上次新下载已 {hours:.1f} 小时 (24小时自动停止)")
        return False

    def run_once(self, keywords: List[str]) -> int:
        """运行一轮搜索，返回新增下载数"""
        # 等待爬虫空闲
        while True:
            status = self.get_api_status()
            if not status.get('running', False):
                break
            print("[等待] 爬虫运行中，等待60秒...")
            time.sleep(60)

        # 启动搜索
        if not self.start_download(keywords):
            return 0

        # 等待完成
        new_count = self.wait_for_complete(timeout_minutes=60)

        # 标记为已搜索
        for kw in keywords:
            self.searched_keywords.add(kw)

        return new_count

    def run(self):
        """主循环"""
        print("=" * 60)
        print("裂变式快穿小说下载器启动")
        print("=" * 60)
        print(f"初始关键词池: {len(self.keyword_pool)} 个")
        print(f"已搜索历史: {len(self.searched_keywords)} 个")
        print(f"上次新下载: {self.last_new_download_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        while True:
            self.round_count += 1
            print(f"\n{'=' * 60}")
            print(f"第 {self.round_count} 轮裂变搜索")
            print(f"{'=' * 60}")

            # 1. 检查是否应该停止
            if self.should_stop():
                break

            # 2. 从文件名提取新关键词
            file_keywords = self.extract_from_filenames()
            self.keyword_pool.update(file_keywords)

            # 3. 裂变生成新关键词
            fission_keywords = self.generate_fission_keywords()
            self.keyword_pool.update(fission_keywords)

            # 4. 选取未搜索过的关键词（每轮最多10个）
            candidates = [
                kw for kw in self.keyword_pool
                if kw not in self.searched_keywords
            ]

            if not candidates:
                print("[警告] 没有新关键词可搜索，裂变更多...")
                # 强制裂变
                extra = self.generate_fission_keywords()
                candidates = list(extra)
                if not candidates:
                    print("[停止] 无法生成更多关键词")
                    break

            # 随机打乱，优先短关键词（更容易命中）
            random.shuffle(candidates)
            candidates.sort(key=len)
            batch = candidates[:10]

            print(f"[批次] 本轮搜索: {batch}")

            # 5. 执行搜索
            new_count = self.run_once(batch)
            self.total_downloaded += new_count

            # 6. 如果有新下载，更新时间
            if new_count > 0:
                self.last_new_download_time = datetime.now()
                print(f"[成功] 本轮新增 {new_count} 本，重置24小时计时器")
            else:
                print(f"[结果] 本轮无新下载")

            # 7. 保存历史
            self.save_history()

            # 8. 短暂休息
            rest = random.randint(5, 15)
            print(f"[休息] 等待 {rest} 秒后继续...")
            time.sleep(rest)

        print("\n" + "=" * 60)
        print("裂变下载器已停止")
        print(f"总轮次: {self.round_count}")
        print(f"总下载: {self.total_downloaded}")
        print(f"总关键词: {len(self.keyword_pool)}")
        print(f"已搜索: {len(self.searched_keywords)}")
        print("=" * 60)
        self.save_history()


if __name__ == '__main__':
    import re
    crawler = FissionCrawler()
    try:
        crawler.run()
    except KeyboardInterrupt:
        print("\n[中断] 用户手动停止")
        crawler.save_history()
    except Exception as e:
        print(f"\n[错误] {e}")
        crawler.save_history()
        raise
