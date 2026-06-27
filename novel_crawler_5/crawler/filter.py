"""
智能内容过滤器 — 接受任何世界主题词
支持：书名匹配、简介匹配、正文强信号、弱信号+辅助词双重验证
"""
import re
import json
from pathlib import Path
from typing import Optional, List


class NovelFilter:
    """小说类型过滤器，通过关键词列表匹配是否包含任一世界主题词"""

    def __init__(self, config_path: Optional[Path] = None):
        self.patterns = {}
        self.keywords: List[str] = []
        self._compile_patterns(config_path)

    def _compile_patterns(self, config_path: Optional[Path]):
        if config_path and config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            regex_cfg = cfg.get("search", {}).get("regex_filter", {})
            self.keywords = cfg.get("search", {}).get("keywords", [])
        else:
            regex_cfg = self._default_patterns()
            self.keywords = []

        for name, pattern_str in regex_cfg.items():
            try:
                self.patterns[name] = re.compile(pattern_str, re.IGNORECASE)
            except re.error as e:
                print(f"[Filter] 正则编译失败 [{name}]: {e}")

    def _default_patterns(self) -> dict:
        return {
            "title": r"(快穿|无限流|综影视|综漫|世界穿梭|穿书攻略|炮灰攻略|副本攻略|穿越万界|万界穿行|位面穿越|多世界)[^，,。]{0,15}|穿越(万界|诸界|多世界)|副本(攻略|通关)|炮灰(逆袭|攻略|系统)",
            "intro": r"【(快穿|无限流)[^】]{0,20}】|快穿\+|炮灰攻略系统|世界任务|每个世界都|穿越[不同各]{0,2}世界|副本(攻略|通关|完成)|积分兑换",
            "content_strong": r"第[一二三四五六七八九十百零\d]+个世界|世界[一二三四五六七八九十\d][：:：]|(下一个?|下个)(世界|副本)|(世界|副本)(完成|结束|通关)|(进入|来到)了?第[一二三四五六七八九十百零\d]+(个)?(世界|副本)",
            "content_weak": r"(恭喜宿主|任务(完成|失败)|宿主[，,。！!])",
            "content_booster": r"(快穿|无限流|副本完成|下一个世界|穿越世界|积分兑换|炮灰攻略系统)",
            "all_combined": r"快穿|无限流|综影视|综漫|炮灰攻略|穿书攻略|副本攻略|穿越万界|万界穿行|位面穿越|世界穿梭|多世界|【(快穿|无限流)[^】]{0,20}】|快穿\+|炮灰攻略系统|世界任务|每个世界都|穿越[不同各]{0,2}世界|副本(攻略|通关|完成)|积分兑换|第[一二三四五六七八九十百零\d]+个世界|世界[一二三四五六七八九十\d][：:：]|(下一个?|下个)(世界|副本)|(世界|副本)(完成|结束|通关)",
        }

    def check_title(self, title: str) -> tuple[bool, str]:
        """检查书名是否匹配"""
        p = self.patterns.get("title")
        if not p:
            return False, ""
        m = p.search(title)
        return (True, m.group()) if m else (False, "")

    def check_intro(self, intro: str) -> tuple[bool, str]:
        """检查简介/标签是否匹配"""
        p = self.patterns.get("intro")
        if not p:
            return False, ""
        m = p.search(intro)
        return (True, m.group()) if m else (False, "")

    def check_content(self, content: str) -> tuple[bool, str, str]:
        """
        检查正文内容，分两级判断：
        1. 强信号：多世界切换 — 单独命中即判定
        2. 弱信号 + 辅助词 — 双重命中才判定
        返回: (是否命中, 级别, 匹配内容)
        """
        p_strong = self.patterns.get("content_strong")
        if p_strong:
            m = p_strong.search(content)
            if m:
                return True, "strong", m.group()

        p_weak = self.patterns.get("content_weak")
        p_boost = self.patterns.get("content_booster")
        if p_weak and p_boost:
            w = p_weak.search(content)
            b = p_boost.search(content)
            if w and b:
                return True, "weak+booster", f"{w.group()} + {b.group()}"

        return False, "", ""

    def _hit_any_keyword(self, text: str) -> tuple[bool, str]:
        """检查文本是否包含任意一个世界主题关键词"""
        if not text:
            return False, ""
        for kw in self.keywords:
            if kw and kw in text:
                return True, kw
        return False, ""

    def is_kuai_chuan(
        self,
        title: str = "",
        intro: str = "",
        content: str = "",
    ) -> tuple[bool, str, str]:
        """
        综合判断是否包含任意世界主题词
        返回: (是否命中, 命中方法, 匹配详情)
        """
        hit, kw = self._hit_any_keyword(title)
        if hit:
            return True, "书名关键词", kw

        hit, kw = self._hit_any_keyword(intro)
        if hit:
            return True, "简介关键词", kw

        hit, method, detail = self.check_content(content)
        if hit:
            return True, method, detail

        return False, "", ""


def create_filter(config_path: Optional[Path] = None) -> NovelFilter:
    return NovelFilter(config_path)
