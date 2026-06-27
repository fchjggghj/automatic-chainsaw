"""通用搜索处理器 — 兜底处理器，使用通用方法搜索和解析"""
import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
from typing import Optional

from .base import BaseSiteHandler, SiteConfig, SearchResult


class GenericHandler(BaseSiteHandler):
    """通用搜索处理器：使用通用方法搜索和解析各种站点"""

    # 额外的搜索入口
    novel_sites = [
        {"name": "笔趣阁通用", "url": "https://www.biquge.com.cn/search.php?keyword={keyword}"},
        {"name": "搜书网", "url": "https://www.soushu.vip/search.html?keyword={keyword}"},
        {"name": "全本小说网通用", "url": "https://www.quanben.com/search?keyword={keyword}"},
        {"name": "笔趣阁5200", "url": "https://www.biquge5200.com/search.php?keyword={keyword}"},
        {"name": "新笔趣阁通用", "url": "https://www.xbiquge.com/search.php?keyword={keyword}"},
        {"name": "爱笔趣阁通用", "url": "https://www.ibiquge.net/search.html?keyword={keyword}"},
        {"name": "顶点小说通用", "url": "https://www.ddxsss.com/search.html?keyword={keyword}"},
        {"name": "八一中文通用", "url": "https://www.81zw.com/search.html?keyword={keyword}"},
        {"name": "小说大全", "url": "https://www.xsqd.com/search.html?keyword={keyword}"},
        {"name": "书库网", "url": "https://www.shuku.net/search.html?keyword={keyword}"},
        {"name": "阅读网", "url": "https://www.yuedu.com/search.html?keyword={keyword}"},
        {"name": "书香门第", "url": "https://www.sxmd.com/search.html?keyword={keyword}"},
        {"name": "小说阅读网", "url": "https://www.readnovel.com/search.html?keyword={keyword}"},
        {"name": "起点中文网", "url": "https://www.qidian.com/search?kw={keyword}"},
        {"name": "纵横中文网", "url": "https://www.zongheng.com/search?keyword={keyword}"},
        {"name": "17K小说网", "url": "https://www.17k.com/search.html?keyword={keyword}"},
        {"name": "晋江通用", "url": "https://www.jjwxc.net/search.php?keyword={keyword}"},
        {"name": "书旗网", "url": "https://www.shuqi.com/search?keyword={keyword}"},
        {"name": "番茄小说", "url": "https://fanqienovel.com/search?keyword={keyword}"},
        {"name": "读书网", "url": "https://www.dushu.com/search.html?keyword={keyword}"},
        {"name": "小说屋", "url": "https://www.xiaoshuowu.com/search.html?keyword={keyword}"},
        {"name": "书海网", "url": "https://www.shuhai.com/search.html?keyword={keyword}"},
        {"name": "奇书网通用", "url": "https://www.qisuwang.com/?s={keyword}"},
        {"name": "小说下载网", "url": "https://www.xsxz.com/search.html?keyword={keyword}"},
        {"name": "爱看书", "url": "https://www.ikanshu.com/search.html?keyword={keyword}"},
        {"name": "天天中文", "url": "https://www.ttzw.com/search.html?keyword={keyword}"},
        {"name": "小说族", "url": "https://www.xiaoshuozu.com/search.html?keyword={keyword}"},
        {"name": "文轩网", "url": "https://www.winxuan.com/search?keyword={keyword}"},
        {"name": "书客网", "url": "https://www.shuke.com/search.html?keyword={keyword}"},
        {"name": "小说馆", "url": "https://www.xiaoshuoguan.com/search.html?keyword={keyword}"},
        {"name": "小说520", "url": "https://www.xs520.com/search.html?keyword={keyword}"},
        {"name": "墨缘文学", "url": "https://www.moyan.com/search.html?keyword={keyword}"},
        {"name": "看书网", "url": "https://www.kanshu.com/search.html?keyword={keyword}"},
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
        """搜索所有通用站点，带翻页"""
        results = []
        seen = set()
        for site in self.novel_sites:
            page = 1
            max_page = 50
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
                soup = BeautifulSoup(html, "html.parser")
                page_results = 0
                for sel in ["a[href*='book']", "a[href*='info']", "a[href*='detail']",
                            ".result a", ".list a", "article a", "h3 a", "h2 a"]:
                    for a in soup.select(sel):
                        title = self.clean_html(a.get_text())
                        href = a.get("href", "")
                        if not title or not href or len(title) < 3 or title in seen:
                            continue
                        if href.startswith("javascript") or href.startswith("#"):
                            continue
                        seen.add(title)
                        results.append(SearchResult(title=title, url=urljoin(base_url, href), source=site["name"]))
                        page_results += 1
                if page_results == 0:
                    for a in soup.find_all("a", href=True):
                        t = self.clean_html(a.get_text())
                        if keyword in t and 3 < len(t) < 60 and t not in seen:
                            seen.add(t)
                            results.append(SearchResult(title=t, url=urljoin(base_url, a["href"]), source=site["name"]))
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
        title_tag = soup.select_one("h1, h2, .title h1, #info h1")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for el in soup.select(".author, #info p, .info span, .meta"):
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
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text().strip()
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT"]):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if re.search(r"(download|down)", a.get("href", ""), re.I):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
