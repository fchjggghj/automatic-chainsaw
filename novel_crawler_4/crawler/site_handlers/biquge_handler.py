"""笔趣阁专用处理器 — 针对笔趣阁系站点优化搜索和解析"""
import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
from typing import Optional

from .base import BaseSiteHandler, SiteConfig, SearchResult


class BiqugeHandler(BaseSiteHandler):
    """笔趣阁专用处理器：精准解析笔趣阁系站点"""

    SITES = [
        {"name": "笔趣阁", "url": "https://www.biquge.com.cn/search.php?keyword={keyword}"},
        {"name": "笔趣阁info", "url": "https://www.biquge.info/search.html?keyword={keyword}"},
        {"name": "新笔趣阁", "url": "https://www.xbiquge.com/search.php?keyword={keyword}"},
        {"name": "爱笔趣阁", "url": "https://www.ibiquge.net/search.html?keyword={keyword}"},
        {"name": "笔趣阁5200", "url": "https://www.biquge5200.com/search.php?keyword={keyword}"},
        {"name": "笔趣阁x", "url": "https://www.biqugex.com/search.html?keyword={keyword}"},
        {"name": "笔趣阁co", "url": "https://www.biquge.co/search.html?keyword={keyword}"},
        {"name": "笔趣读", "url": "https://www.biqudu.com/search.html?keyword={keyword}"},
        {"name": "笔趣阁wx", "url": "https://www.biquwx.com/search.html?keyword={keyword}"},
        {"name": "书包网", "url": "https://www.shubao456.com/search.html?keyword={keyword}"},
        {"name": "奇书塔", "url": "https://www.qishuta.com/search.html?keyword={keyword}"},
        {"name": "小说笔趣阁", "url": "https://www.xsbiquge.com/search.php?keyword={keyword}"},
        {"name": "全本小说网", "url": "https://www.quanben.com/search?keyword={keyword}"},
        {"name": "读全本", "url": "https://www.duquanben.com/search.php?keyword={keyword}"},
    ]

    def __init__(self, config: SiteConfig, timeout: int = 30, delay: float = 1.5):
        super().__init__(config, timeout)
        self.delay = delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                }
            )
        return self._session

    async def _fetch(self, url: str) -> Optional[str]:
        try:
            session = await self._get_session()
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status == 200:
                    return await resp.text(errors='ignore')
        except Exception:
            pass
        return None

    async def search(self, keyword: str, max_results: int = 999999) -> list[SearchResult]:
        """搜索所有笔趣阁系站点，带翻页"""
        results = []
        seen = set()
        for site in self.SITES:
            page = 1
            max_page = 100
            base_url = re.match(r'(https?://[^/]+/)', site["url"]).group(1)
            
            while page <= max_page and len(results) < max_results:
                url = site["url"].format(keyword=quote(keyword))
                if page > 1:
                    if '?' in url:
                        url += f"&page={page}"
                    else:
                        url += f"?page={page}"
                html = await self._fetch(url)
                if not html:
                    break
                site_results = self._parse_search_page(html, base_url, site["name"])
                new_results = [r for r in site_results if r.title not in seen]
                for r in new_results:
                    seen.add(r.title)
                results.extend(new_results)
                
                if len(new_results) == 0:
                    break
                
                soup = BeautifulSoup(html, "html.parser")
                found_max = self.find_max_page(soup, page)
                if found_max <= page:
                    break
                max_page = min(max_page, found_max)
                page += 1
                await asyncio.sleep(self.delay)
            await asyncio.sleep(self.delay)
        return results[:max_results]

    def _parse_search_page(self, html: str, base_url: str, site_name: str) -> list[SearchResult]:
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # 结构1: result-item / resultgame
        for item in soup.select(".result-item, .resultgame, .novelslist2 li, .search-list li"):
            title_tag = item.select_one("a[href], .result-game-item-title a, .bookname a")
            if not title_tag:
                title_tag = item.select_one("a")
            if not title_tag:
                continue
            title = self.clean_html(title_tag.get_text())
            href = title_tag.get("href", "")
            if not title or not href or len(title) < 2:
                continue
            full_url = urljoin(base_url, href)
            author = ""
            author_tag = item.select_one(".result-game-item-author, .author, span")
            if author_tag:
                author = self.clean_html(author_tag.get_text())
                author = re.sub(r'^.*作者[：:]\s*', '', author).strip()
            intro = ""
            intro_tag = item.select_one(".result-game-item-desc, .intro, .bookintro")
            if intro_tag:
                intro = self.clean_html(intro_tag.get_text())[:300]
            results.append(SearchResult(title=title, author=author, url=full_url, intro=intro, source=site_name))

        # 结构2: 简单链接列表
        if not results:
            for link in soup.select("h3 a, h2 a, .bookname a, dl a")[:50]:
                title = self.clean_html(link.get_text())
                href = link.get("href", "")
                if title and href and len(title) > 2:
                    full_url = urljoin(base_url, href)
                    results.append(SearchResult(title=title, url=full_url, source=site_name))

        return results

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        intro = ""
        title_tag = soup.select_one("#info h1, h1, .bookname h1")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for p in soup.select("#info p"):
            text = self.clean_html(p.get_text())
            if "作者" in text:
                author = re.sub(r'^.*作者[：:]\s*', '', text).strip()
                break
        intro_tag = soup.select_one("#intro, .intro")
        if intro_tag:
            intro = self.clean_html(intro_tag.get_text())[:500]
        return {"title": title, "author": author, "intro": intro, "url": url}

    async def get_download_url(self, novel_url: str) -> Optional[str]:
        # 笔趣阁通常没有直接下载链接
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
