"""
站点处理器基类 — 插件化架构，每个目标网站实现自己的处理器
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    author: str = ""
    url: str = ""
    download_url: str = ""
    intro: str = ""
    category: str = ""
    source: str = ""
    file_format: str = ""


@dataclass
class SiteConfig:
    """站点配置"""
    name: str
    base_url: str
    search_url: str = ""
    enabled: bool = True


class BaseSiteHandler(ABC):
    """站点处理器基类"""

    def __init__(self, config: SiteConfig, timeout: int = 30):
        self.config = config
        self.timeout = timeout

    @abstractmethod
    async def search(self, keyword: str, max_results: int = 20) -> list[SearchResult]:
        """搜索小说，返回结果列表"""
        ...

    @abstractmethod
    async def get_download_url(self, novel_url: str) -> Optional[str]:
        """从小说详情页提取下载链接"""
        ...

    @abstractmethod
    async def get_novel_info(self, url: str) -> Optional[dict]:
        """获取小说详情（标题、作者、简介等）"""
        ...

    def build_search_url(self, keyword: str) -> Optional[str]:
        if not self.config.search_url:
            return None
        return self.config.search_url.format(keyword=keyword)

    def is_valid_result(self, result: SearchResult) -> bool:
        return bool(result.title and result.url)

    @staticmethod
    def clean_html(text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def extract_txt_links(html: str) -> list[str]:
        """从HTML中提取所有TXT下载链接"""
        links = set()
        for m in re.finditer(r'href=["\']([^"\']+\.txt(?:\?[^"\']*)?)["\']', html, re.I):
            links.add(m.group(1))
        for m in re.finditer(r'href=["\']([^"\']*download[^"\']*)["\']', html, re.I):
            links.add(m.group(1))
        for m in re.finditer(r'href=["\']([^"\']*down[^"\']*\.(?:txt|zip|rar))["\']', html, re.I):
            links.add(m.group(1))
        for m in re.finditer(r'onclick=["\'].*?(?:download|down)["\']', html, re.I):
            pass
        return list(links)

    @staticmethod
    def extract_download_buttons(html: str) -> list[tuple[str, str]]:
        """提取下载按钮: [(链接, 按钮文本)]"""
        results = []
        patterns = [
            r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            r'<button[^>]*onclick=["\'].*?location\s*=\s*["\']([^"\']+)["\'].*?>(.*?)</button>',
            r'<a[^>]*href=["\']([^"\']+\.(?:txt|zip|rar))["\'][^>]*>(.*?)</a>',
        ]
        for pattern in patterns:
            for m in re.finditer(pattern, html, re.I | re.S):
                url = m.group(1).strip()
                text = BaseSiteHandler.clean_html(m.group(2))
                if any(kw in text for kw in ["下载", "download", "TXT", "txt", "全本"]):
                    results.append((url, text))
        return results

    @staticmethod
    def find_max_page(soup, current_page: int = 1) -> int:
        """从HTML中找出最大页码（通用翻页检测）"""
        max_page = current_page
        # 方法1: 找所有页码链接 /page/N /p/N ?page=N 等
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            # 常见翻页格式
            for pattern in [r'page[=/](\d+)', r'p[=/](\d+)', r'[?&]page=(\d+)',
                           r'[?&]p=(\d+)', r'_(\d+)\.html?$', r'/(\d+)\.html?$']:
                m = re.search(pattern, href, re.I)
                if m:
                    pn = int(m.group(1))
                    if pn > max_page:
                        max_page = pn
            # 纯数字文本链接
            text = a.get_text().strip()
            if text.isdigit():
                pn = int(text)
                if pn > max_page:
                    max_page = pn
        # 方法2: 找"下一页"链接 — 从中推算最大页码
        for a in soup.find_all("a", href=True):
            text = a.get_text().strip()
            if text in ('下一页', '下页', 'Next', 'next', '›', '»', '>'):
                href = a.get("href", "")
                for pattern in [r'page[=/](\d+)', r'p[=/](\d+)', r'[?&]page=(\d+)',
                               r'[?&]p=(\d+)', r'_(\d+)\.html?$', r'/(\d+)\.html?$']:
                    m = re.search(pattern, href, re.I)
                    if m:
                        pn = int(m.group(1))
                        if pn > max_page:
                            max_page = pn
        # 方法3: 找"末页"链接
        for a in soup.find_all("a", href=True):
            text = a.get_text().strip()
            if text in ('末页', '最后一页', 'Last', 'last'):
                href = a.get("href", "")
                for pattern in [r'page[=/](\d+)', r'p[=/](\d+)', r'[?&]page=(\d+)',
                               r'[?&]p=(\d+)', r'_(\d+)\.html?$', r'/(\d+)\.html?$']:
                    m = re.search(pattern, href, re.I)
                    if m:
                        pn = int(m.group(1))
                        if pn > max_page:
                            max_page = pn
        return max_page
