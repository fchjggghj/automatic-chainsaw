"""TXT下载站专用处理器 — 针对提供TXT直接下载的站点"""
import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
from typing import Optional

from .base import BaseSiteHandler, SiteConfig, SearchResult


class TxtDownloadHandler(BaseSiteHandler):
    """TXT下载站处理器：搜小说、256文库等"""

    SITES = [
        {"name": "搜小说", "base_url": "https://www.soxs.cc/", "search_url": "https://www.soxs.cc/search.html?keyword={keyword}"},
        {"name": "256文库", "base_url": "https://www.256wenku.com/", "search_url": "https://www.256wenku.com/search.html?keyword={keyword}"},
        {"name": "天下吧唱", "base_url": "https://www.txbarc.com/", "search_url": "https://www.txbarc.com/search.html?keyword={keyword}"},
        {"name": "爱小说", "base_url": "https://www.aixiaoshuo.com/", "search_url": "https://www.aixiaoshuo.com/search.html?keyword={keyword}"},
        {"name": "酷笔趣", "base_url": "https://www.kubiqu.com/", "search_url": "https://www.kubiqu.com/search.html?keyword={keyword}"},
        {"name": "23小说网", "base_url": "https://www.23xs.cc/", "search_url": "https://www.23xs.cc/search.html?keyword={keyword}"},
        {"name": "八一中文", "base_url": "https://www.81zw.com/", "search_url": "https://www.81zw.com/search.html?keyword={keyword}"},
        {"name": "顶点小说", "base_url": "https://www.ddxsss.com/", "search_url": "https://www.ddxsss.com/search.html?keyword={keyword}"},
        {"name": "笔趣阁la", "base_url": "https://www.biqugela.com/", "search_url": "https://www.biqugela.com/search.html?keyword={keyword}"},
        {"name": "书txt网", "base_url": "https://www.shutxt.com/", "search_url": "https://www.shutxt.com/search.html?keyword={keyword}"},
        {"name": "文学迷", "base_url": "https://www.wenxuemi.com/", "search_url": "https://www.wenxuemi.com/search.html?keyword={keyword}"},
        {"name": "宝林苑", "base_url": "https://www.baolinyuan.com/", "search_url": "https://www.baolinyuan.com/search.html?keyword={keyword}"},
    ]

    def __init__(self, config: SiteConfig, timeout: int = 30, delay: float = 1.5):
        super().__init__(config, timeout)
        self.delay = delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(connector=conn, timeout=timeout, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            })
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
        """搜索所有TXT下载站，带翻页"""
        results = []
        seen = set()
        for site in self.SITES:
            page = 1
            max_page = 100
            while page <= max_page and len(results) < max_results:
                url = site["search_url"].format(keyword=quote(keyword))
                if page > 1:
                    if '?' in url:
                        url += f"&page={page}"
                    else:
                        url += f"?page={page}"
                html = await self._fetch(url)
                if not html:
                    break
                soup = BeautifulSoup(html, "html.parser")
                page_results = 0
                for sel in ["a[href*='book']", "a[href*='info']", "a[href*='detail']",
                            ".result a", ".list a", "article a", "h3 a", "h2 a",
                            "a[href*='novel']", "a[href*='down']"]:
                    for a in soup.select(sel):
                        title = self.clean_html(a.get_text())
                        href = a.get("href", "")
                        if not title or not href or len(title) < 3 or title in seen:
                            continue
                        if href.startswith("javascript") or href.startswith("#"):
                            continue
                        seen.add(title)
                        results.append(SearchResult(title=title, url=urljoin(site["base_url"], href), source=site["name"]))
                        page_results += 1
                if page_results == 0:
                    for a in soup.find_all("a", href=True):
                        t = self.clean_html(a.get_text())
                        if keyword in t and 3 < len(t) < 60 and t not in seen:
                            seen.add(t)
                            results.append(SearchResult(title=t, url=urljoin(site["base_url"], a["href"]), source=site["name"]))
                            page_results += 1
                    if page_results == 0:
                        break
                found_max = self.find_max_page(soup, page)
                if found_max <= page:
                    break
                max_page = min(max_page, found_max)
                page += 1
                await asyncio.sleep(self.delay)
            await asyncio.sleep(self.delay)
        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        title_tag = soup.select_one("h1, h2, .bookname h1, #info h1")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for el in soup.select(".author, #info p, .info span"):
            text = self.clean_html(el.get_text())
            if "作者" in text:
                author = re.sub(r'^.*(?:作者|author)[：:\s]*', '', text).strip()
                break
        intro = ""
        intro_tag = soup.select_one(".intro, #intro, .description")
        if intro_tag:
            intro = self.clean_html(intro_tag.get_text())[:500]
        return {"title": title, "author": author, "intro": intro, "url": url}

    async def get_download_url(self, novel_url: str) -> Optional[str]:
        html = await self._fetch(novel_url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for sel in [".download a", ".btn-down a", "a.download", "a.btn-download", "[class*=download] a"]:
            for a in soup.select(sel):
                href = a.get("href", "")
                if href and not href.startswith("javascript"):
                    return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text().strip()
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT"]):
                return urljoin(novel_url, href)
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
