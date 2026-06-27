"""
专用小说站点处理器 — 逐一适配的网站
根据实际探测结果分为以下类别：
  - 帝国CMS类（POST搜索）：贼吧网、9奇书、熬夜下载、奇书de、ijj小说、精校吧、爱悦读
  - WordPress类：精校全本
  - 自建搜索：小说下载吧、宝书网等
  - 特殊站点：好读、知轩藏书、TXT图书下载网、熊猫搜书
  - 新增适配：爱下电子书、更多下载站
"""
import re
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
from typing import Optional

from .base import BaseSiteHandler, SiteConfig, SearchResult


class ZhixuanHandler(BaseSiteHandler):
    """知轩藏书 (zxcs.me) — 精校TXT下载站，服务器不稳定"""
    
    SEARCH_URLS = [
        "http://zxcs.me/index.php?keyword={keyword}",
        "http://zxcs.me/?keyword={keyword}",
    ]
    BASE_URL = "http://zxcs.me/"

    def __init__(self, config: SiteConfig, timeout: int = 30, delay: float = 1.5):
        super().__init__(config, timeout)
        self.delay = delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=conn, timeout=timeout, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
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
        results = []
        seen = set()
        page = 1
        max_page = 200

        for url_tpl in self.SEARCH_URLS:
            page = 1
            while page <= max_page and len(results) < max_results:
                url = url_tpl.format(keyword=quote(keyword))
                if page > 1:
                    if '?' in url:
                        url += f"&page={page}"
                    else:
                        url += f"/page/{page}"
                html = await self._fetch(url)
                if not html:
                    break
                soup = BeautifulSoup(html, "html.parser")
                page_results = 0
                for item in soup.select(".list-item, .item, article, .post"):
                    title_a = item.select_one("h2 a, h3 a, .title a, a")
                    if not title_a:
                        continue
                    title = self.clean_html(title_a.get_text())
                    href = title_a.get("href", "")
                    if not title or not href or title in seen:
                        continue
                    seen.add(title)
                    full_url = urljoin(self.BASE_URL, href)
                    results.append(SearchResult(title=title, url=full_url, source="知轩藏书"))
                    page_results += 1
                if page_results == 0:
                    for a in soup.find_all("a", href=True):
                        t = self.clean_html(a.get_text())
                        if keyword in t and 3 < len(t) < 60 and t not in seen:
                            seen.add(t)
                            full_url = urljoin(self.BASE_URL, a["href"])
                            results.append(SearchResult(title=t, url=full_url, source="知轩藏书"))
                            page_results += 1
                    if page_results == 0:
                        break
                found_max = self.find_max_page(soup, page)
                if found_max <= page:
                    break
                max_page = min(max_page, found_max)
                page += 1
                await asyncio.sleep(self.delay)
            if results:
                break
        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        intro = ""
        title_tag = soup.select_one("h1, .title h1, .post-title")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for el in soup.select(".author, .meta, #info p"):
            text = self.clean_html(el.get_text())
            if "作者" in text:
                author = re.sub(r'^.*(?:作者|author)[：:\s]*', '', text).strip()
                break
        intro_tag = soup.select_one(".intro, .description, #intro, .excerpt")
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
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(
                kw in text for kw in ["下载", "TXT", "全本"]
            ):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if re.search(r"(download|down)", a.get("href", ""), re.I):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class EmpireCmsHandler(BaseSiteHandler):
    """帝国CMS类站点通用处理器 — POST搜索"""
    
    SITES = [
        {"name": "贼吧网", "base_url": "https://www.zei8.vip/",
         "search_action": "/e/sch/", "params": {"keyboard": "{keyword}"}, "show_field": "title", "tbname": "download"},
        {"name": "9奇书", "base_url": "https://www.9qishu.com/",
         "search_action": "/e/search/index.php", "params": {"keyboard": "{keyword}", "Submit22": "搜索", "tbname": "title", "tempid": "1", "show": "title"}},
        {"name": "熬夜下载", "base_url": "https://www.aoyedown.com/",
         "search_action": "/e/search/", "params": {"keyboard": "{keyword}", "Submit22": "搜索", "tbname": "download", "tempid": "1"}},
        {"name": "奇书de", "base_url": "https://www.qishu.de/",
         "search_action": "/e/search/index.php", "params": {"show": "title,smalltext,writer", "tbname": "txt", "tempid": "1", "keyboard": "{keyword}", "Submit22": "搜索"}},
        {"name": "ijj小说", "base_url": "https://www.ijjxsxzw.com/",
         "search_action": "/e/search/index.php", "params": {"show": "title", "tbname": "title", "tempid": "1", "orderby": "newstime", "myorder": "0", "keyboard": "{keyword}"}, "need_login": True},
        {"name": "精校吧", "base_url": "https://www.jingjiaoba.com/",
         "search_action": "/e/search/index.php", "params": {"keyboard": "{keyword}", "Submit22": "搜索", "tbname": "title", "tempid": "1"}},
        {"name": "爱悦读", "base_url": "https://www.iyd.wang/",
         "search_action": "/e/search/", "params": {"keyboard": "{keyword}", "Submit22": "搜索", "tbname": "title", "tempid": "1"}},
        {"name": "勤看书", "base_url": "https://www.qinkan.net/",
         "search_action": "/e/search/index.php", "params": {"show": "title", "tbname": "title", "tempid": "1", "keyboard": "{keyword}", "Submit22": "搜索"}},
        {"name": "爱下书", "base_url": "https://www.aixiashu.info/",
         "search_action": "/e/search/index.php", "params": {"keyboard": "{keyword}", "Submit22": "搜索", "tbname": "title", "tempid": "1", "show": "title"}},
    ]

    def __init__(self, config: SiteConfig, timeout: int = 30, delay: float = 1.5):
        super().__init__(config, timeout)
        self.delay = delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=conn, timeout=timeout, headers={
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

    async def _post_search(self, url: str, data: dict) -> Optional[str]:
        try:
            session = await self._get_session()
            async with session.post(url, data=data, allow_redirects=True) as resp:
                if resp.status == 200:
                    return await resp.text(errors='ignore')
        except Exception:
            pass
        return None

    async def search(self, keyword: str, max_results: int = 999999) -> list[SearchResult]:
        results = []
        for site in self.SITES:
            if site.get("need_login"):
                try:
                    html = await self._fetch(site["base_url"])
                    if html:
                        soup = BeautifulSoup(html, "html.parser")
                        site_results = self._parse_empire_results(soup, site["base_url"], site["name"], keyword)
                        results.extend(site_results)
                except Exception:
                    pass
                await asyncio.sleep(self.delay)
                continue
            
            search_url = urljoin(site["base_url"], site["search_action"])
            post_data = {}
            for k, v in site["params"].items():
                post_data[k] = v.replace("{keyword}", keyword) if isinstance(v, str) else v
            
            html = await self._post_search(search_url, post_data)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                is_info_page = False
                title_tag = soup.title
                if title_tag and "信息提示" in title_tag.get_text():
                    is_info_page = True
                if is_info_page:
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if href and not href.startswith("javascript"):
                            jump_html = await self._fetch(urljoin(site["base_url"], href))
                            if jump_html:
                                soup = BeautifulSoup(jump_html, "html.parser")
                                is_info_page = False
                                break
                if not is_info_page:
                    site_results = self._parse_empire_results(soup, site["base_url"], site["name"], keyword)
                    results.extend(site_results)
            
            if not any(r.source == site["name"] for r in results):
                get_search_urls = [
                    f"{site['base_url']}e/search/index.php?keyboard={quote(keyword)}&show=title&tbname={site['params'].get('tbname', 'title')}&tempid=1",
                    f"{site['base_url']}search.html?keyword={quote(keyword)}",
                    f"{site['base_url']}?s={quote(keyword)}",
                ]
                for get_url in get_search_urls:
                    html = await self._fetch(get_url)
                    if not html:
                        continue
                    soup = BeautifulSoup(html, "html.parser")
                    site_results = self._parse_empire_results(soup, site["base_url"], site["name"], keyword)
                    if site_results:
                        results.extend(site_results)
                        break
            
            await asyncio.sleep(self.delay)
        
        return results[:max_results]

    def _parse_empire_results(self, soup, base_url, site_name, keyword):
        results = []
        selectors = [
            ".searchlist li", ".listbox .ebox", ".search-result li",
            ".list-item", ".con li", "ul.list li", ".movie-item",
            "li", ".ebox",
        ]
        for sel in selectors:
            items = soup.select(sel)
            if len(items) < 1:
                continue
            for item in items:
                title_a = item.select_one("a[href], h3 a, h4 a, .title a")
                if not title_a:
                    continue
                title = self.clean_html(title_a.get_text())
                href = title_a.get("href", "")
                if not title or not href or len(title) < 2:
                    continue
                full_url = urljoin(base_url, href)
                if full_url.startswith("javascript"):
                    continue
                author = ""
                for el in item.select(".author, .info, span, p, .smalltext"):
                    text = self.clean_html(el.get_text())
                    if "作者" in text:
                        author = re.sub(r'^.*(?:作者|author)[：:\s]*', '', text).strip()
                        break
                results.append(SearchResult(title=title, author=author, url=full_url, source=site_name))
            if results:
                break
        return results

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        intro = ""
        title_tag = soup.select_one("h1, .title h1, .info h1, h2")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for el in soup.select(".author, #info p, .info span, .writer"):
            text = self.clean_html(el.get_text())
            if "作者" in text:
                author = re.sub(r'^.*(?:作者|author)[：:\s]*', '', text).strip()
                break
        intro_tag = soup.select_one(".intro, .description, #intro, .excerpt")
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
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT", "全本"]):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if re.search(r"(download|down)", a.get("href", ""), re.I):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class NovelessHandler(BaseSiteHandler):
    """精校全本 (noveless.com) — WordPress站"""
    BASE_URL = "https://noveless.com/"

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
        results = []
        seen_urls = set()
        page = 1
        max_page = 100

        while page <= max_page and len(results) < max_results:
            url = f"{self.BASE_URL}?s={quote(keyword)}"
            if page > 1:
                url += f"&paged={page}"
            html = await self._fetch(url)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            page_results = 0
            for sel in ["article a[href]", ".post a[href]", ".entry a[href]",
                        ".content article a[href]", ".app-content a[href]",
                        ".tab-content a[href]", ".new-nav-tab-content a[href]"]:
                for a in soup.select(sel):
                    title = self.clean_html(a.get_text())
                    href = a.get("href", "")
                    if not title or not href or len(title) < 4 or len(title) > 80:
                        continue
                    if href.startswith("#") or href.startswith("javascript"):
                        continue
                    if any(kw in title for kw in ["登录", "注册", "搜索", "评论", "主页"]):
                        continue
                    if any(p in href for p in ["/archives/", "/post/", "/p=", "/?p=", "/20", "/article"]):
                        if href not in seen_urls:
                            seen_urls.add(href)
                            results.append(SearchResult(title=title, url=href, source="精校全本"))
                            page_results += 1
            if page_results == 0:
                break
            found_max = self.find_max_page(soup, page)
            if found_max <= page:
                break
            max_page = min(max_page, found_max)
            page += 1
            await asyncio.sleep(self.delay)

        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        title_tag = soup.select_one("h1, .entry-title, .post-title")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for el in soup.select(".author, .meta, .post-meta"):
            text = self.clean_html(el.get_text())
            if "作者" in text:
                author = re.sub(r'^.*(?:作者|author)[：:\s]*', '', text).strip()
                break
        intro = ""
        intro_tag = soup.select_one(".entry-content, .content, .excerpt")
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
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT", "全本"]):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if re.search(r"(download|down)", a.get("href", ""), re.I):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class HaodooHandler(BaseSiteHandler):
    """好读 (haodoo.net) — 繁体中文电子书站"""
    BASE_URL = "https://www.haodoo.net/"

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
        url = f"{self.BASE_URL}?S={quote(keyword)}"
        html = await self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results = []
        seen = set()
        for a in soup.find_all("a", href=True):
            title = self.clean_html(a.get_text())
            href = a.get("href", "")
            if not title or not href or len(title) < 3 or len(title) > 80:
                continue
            if href.startswith("#") or href.startswith("javascript"):
                continue
            if any(p in href for p in [".db=", "?M=", "?B="]):
                if title not in seen:
                    seen.add(title)
                    results.append(SearchResult(title=title, url=urljoin(self.BASE_URL, href), source="好读"))
        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.select_one("h1, h2, title")
        title = self.clean_html(title_tag.get_text()) if title_tag else ""
        return {"title": title, "author": "", "intro": "", "url": url}

    async def get_download_url(self, novel_url: str) -> Optional[str]:
        html = await self._fetch(novel_url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text().strip()
            if "下載" in text or "download" in text.lower() or ".txt" in href or ".updb" in href:
                return urljoin(novel_url, href)
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class Txt8Handler(BaseSiteHandler):
    """小说下载吧 (txt8.net) — 搜索结果丰富"""
    BASE_URL = "http://www.txt8.net/"
    SEARCH_URL = "http://www.txt8.net/search.asp?keyword={keyword}"

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
        results = []
        seen = set()
        page = 1
        max_page = 100

        while page <= max_page and len(results) < max_results:
            url = self.SEARCH_URL.format(keyword=quote(keyword))
            if page > 1:
                url += f"&page={page}"
            html = await self._fetch(url)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            page_results = 0
            for a in soup.select("a[href*='book'], a[href*='novel'], a[href*='info']"):
                title = self.clean_html(a.get_text())
                href = a.get("href", "")
                if not title or not href or len(title) < 3 or title in seen:
                    continue
                seen.add(title)
                results.append(SearchResult(title=title, url=urljoin(self.BASE_URL, href), source="小说下载吧"))
                page_results += 1
            if not page_results:
                for a in soup.find_all("a", href=True):
                    t = self.clean_html(a.get_text())
                    if keyword in t and 3 < len(t) < 60 and t not in seen:
                        seen.add(t)
                        results.append(SearchResult(title=t, url=urljoin(self.BASE_URL, a["href"]), source="小说下载吧"))
                        page_results += 1
                if page_results == 0:
                    break
            found_max = self.find_max_page(soup, page)
            if found_max <= page:
                break
            max_page = min(max_page, found_max)
            page += 1
            await asyncio.sleep(self.delay)

        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        title_tag = soup.select_one("h1, h2, .bookname h1")
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
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text().strip()
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT", "全本"]):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if any(kw in a.get_text() for kw in ["TXT下载", "全文下载", "全本下载", "下载本书"]):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class BookdownHandler(BaseSiteHandler):
    """TXT图书下载网 (bookdown.com.cn / bookshuku.org)"""
    BASE_URLS = ["http://www.bookdown.com.cn/", "http://www.bookshuku.org/"]
    SEARCH_URL = "http://www.bookdown.com.cn/search.asp?keyword={keyword}"

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
        results = []
        seen = set()
        page = 1
        max_page = 100

        while page <= max_page and len(results) < max_results:
            url = self.SEARCH_URL.format(keyword=quote(keyword))
            if page > 1:
                url += f"&page={page}"
            html = await self._fetch(url)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")
            page_results = 0
            for a in soup.select("a[href*='book'], a[href*='info'], a[href*='down']"):
                title = self.clean_html(a.get_text())
                href = a.get("href", "")
                if not title or not href or len(title) < 3 or title in seen:
                    continue
                seen.add(title)
                results.append(SearchResult(title=title, url=urljoin(self.BASE_URLS[0], href), source="TXT图书下载网"))
                page_results += 1
            if not page_results:
                for a in soup.find_all("a", href=True):
                    t = self.clean_html(a.get_text())
                    if keyword in t and 3 < len(t) < 60 and t not in seen:
                        seen.add(t)
                        results.append(SearchResult(title=t, url=urljoin(self.BASE_URLS[0], a["href"]), source="TXT图书下载网"))
                        page_results += 1
                if page_results == 0:
                    break
            found_max = self.find_max_page(soup, page)
            if found_max <= page:
                break
            max_page = min(max_page, found_max)
            page += 1
            await asyncio.sleep(self.delay)

        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        title_tag = soup.select_one("h1, h2, .bookname h1")
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
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text().strip()
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT", "全本"]):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if any(kw in a.get_text() for kw in ["TXT下载", "全文下载", "全本下载"]):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class CustomSearchHandler(BaseSiteHandler):
    """自定义搜索站点 — 20+个GET搜索站"""
    SEARCH_URLS = {
        "宝书网": "https://www.baoshubao.com/search.html?searchkey={keyword}",
        "酷我书": "https://www.kuwushu.com/search.html?searchkey={keyword}",
        "免费小说网": "https://www.mianfeixiaoshuowang.com/search.html?searchkey={keyword}",
        "万卷txt": "https://www.wanjutxt.com/search.html?searchkey={keyword}",
        "哈哈文学": "https://www.hahawx.com/search.html?searchkey={keyword}",
        "完结小说网": "https://www.wanjiewx.com/search.html?searchkey={keyword}",
        "txt139": "http://www.txt139.com/search.asp?keyword={keyword}",
        "渣渣小说网": "http://www.zhazhaz.com/search.html?searchkey={keyword}",
        "80奇书": "http://www.80qishu.com/search.html?searchkey={keyword}",
        "无限小说": "http://www.wuxianxs.com/search.html?searchkey={keyword}",
        "999txt": "http://www.999txt.com/search.html?searchkey={keyword}",
        "小说吧": "http://www.xiaoshuo8.com/search.html?searchkey={keyword}",
        "mashimaro3": "https://mashimaro3.com/bbs/search.php?kw={keyword}",
        "久久小说网": "http://www.jjxsw.com/search.html?searchkey={keyword}",
        "乐读电子书": "http://www.leduwx.com/search.html?searchkey={keyword}",
        "小说之家": "http://www.xszj.com/search.html?searchkey={keyword}",
        "爱书网": "http://www.ishu5.com/search.html?searchkey={keyword}",
        "TXT小说网": "http://www.txtxs.com/search.html?searchkey={keyword}",
        "山西长篇": "http://www.sxcctp.com/search.html?searchkey={keyword}",
        "书籍知识库": "http://www.bookzsk.com/search.html?searchkey={keyword}",
        "棉花糖小说网": "https://www.mhtxss.com/search.html?searchkey={keyword}",
        "当书网": "http://www.downbook.cc/search.html?searchkey={keyword}",
        "下书网": "http://www.xiashuyun.com/search.html?searchkey={keyword}",
        "全本小说网": "http://www.xqb5.org/search.html?searchkey={keyword}",
        "奇书网qishuta": "http://www.qishuta.org/search.html?searchkey={keyword}",
    }

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
        results = []
        seen = set()
        for name, url_tpl in self.SEARCH_URLS.items():
            base_url = re.match(r'(https?://[^/]+/)', url_tpl).group(1)
            page = 1
            max_page = 50
            while page <= max_page and len(results) < max_results:
                url = url_tpl.format(keyword=quote(keyword))
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
                # 通用搜索结果提取
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
                        results.append(SearchResult(title=title, url=urljoin(base_url, href), source=name))
                        page_results += 1
                # 兜底
                if page_results == 0:
                    for a in soup.find_all("a", href=True):
                        t = self.clean_html(a.get_text())
                        if keyword in t and 3 < len(t) < 60 and t not in seen:
                            seen.add(t)
                            results.append(SearchResult(title=t, url=urljoin(base_url, a["href"]), source=name))
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
        title_tag = soup.select_one("h1, h2, .title h1")
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
        for sel in [".download a", ".btn-down a", ".down-btn a", "a.download", "a.btn-download"]:
            for a in soup.select(sel):
                href = a.get("href", "")
                if href and not href.startswith("javascript"):
                    return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text().strip()
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT", "全本"]):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if any(kw in a.get_text() for kw in ["TXT下载", "全文下载", "全本下载", "下载本书"]):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class XmsoushuHandler(BaseSiteHandler):
    """熊猫搜书 (xmsoushu.com) — 聚合搜索引擎"""

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
        url = f"https://xmsoushu.com/search?q={quote(keyword)}"
        html = await self._fetch(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        results = []
        seen = set()
        for a in soup.find_all("a", href=True):
            title = self.clean_html(a.get_text())
            href = a.get("href", "")
            if not title or not href or len(title) < 4 or title in seen:
                continue
            if href.startswith("javascript") or href.startswith("#"):
                continue
            if "xmsoushu" not in href and href.startswith("http"):
                seen.add(title)
                results.append(SearchResult(title=title, url=href, source="熊猫搜书"))
        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        return {"title": "", "author": "", "intro": "", "url": url}

    async def get_download_url(self, novel_url: str) -> Optional[str]:
        return None  # 聚合搜索引擎不直接提供下载

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class Ixdzs8Handler(BaseSiteHandler):
    """爱下电子书 (ixdzs8.com) — 专业TXT下载站，翻页搜索"""

    BASE_URL = "https://ixdzs8.com/"

    def __init__(self, config: SiteConfig, timeout: int = 30, delay: float = 1.5):
        super().__init__(config, timeout)
        self.delay = delay
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=conn, timeout=timeout, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "text/html",
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
        """翻页搜索：/bsearch?q=keyword&page=N"""
        results = []
        seen = set()
        page = 1
        max_page = 200

        while page <= max_page and len(results) < max_results:
            url = f"https://ixdzs8.com/bsearch?q={quote(keyword)}&page={page}"
            html = await self._fetch(url)
            if not html:
                break
            soup = BeautifulSoup(html, "html.parser")

            page_results = 0
            for a in soup.find_all("a", href=True):
                t = self.clean_html(a.get_text())
                h = a.get("href", "")
                if not re.match(r'/read/\d+/?$', h):
                    continue
                if not t or len(t) < 3 or len(t) > 80:
                    continue
                if t in seen:
                    continue
                seen.add(t)
                full_url = urljoin(self.BASE_URL, h)
                results.append(SearchResult(title=t, url=full_url, source="爱下电子书"))
                page_results += 1

            if page_results == 0:
                break

            # 检查是否还有下一页
            has_next = False
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                m = re.search(r'page=(\d+)', href)
                if m and int(m.group(1)) > page:
                    has_next = True
                    break
            if not has_next:
                break

            page += 1
            await asyncio.sleep(self.delay)

        return results[:max_results]

    async def get_novel_info(self, url: str) -> Optional[dict]:
        html = await self._fetch(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        author = ""
        intro = ""
        title_tag = soup.select_one("h1, .book-name, .bookname h1, .novel-title")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for el in soup.select(".author, .book-author, .writer, a[href*='/author/']"):
            text = self.clean_html(el.get_text())
            if text and text != title:
                author = text
                break
        intro_tag = soup.select_one(".book-intro, .intro, .description, #intro, .summary")
        if intro_tag:
            intro = self.clean_html(intro_tag.get_text())[:500]
        return {"title": title, "author": author, "intro": intro, "url": url}

    async def get_download_url(self, novel_url: str) -> Optional[str]:
        html = await self._fetch(novel_url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for sel in [".download a", ".btn-down a", ".down-btn a",
                    "a.download", "a.btn-download",
                    "[class*=download] a", "[class*=down] a",
                    ".book-down a", ".novel-down a"]:
            for a in soup.select(sel):
                href = a.get("href", "")
                if href and not href.startswith("javascript"):
                    dl_url = urljoin(novel_url, href)
                    if dl_url.endswith(".txt") or ".zip" in dl_url or "download" in dl_url.lower():
                        return dl_url
                    dl_html = await self._fetch(dl_url)
                    if dl_html:
                        dl_soup = BeautifulSoup(dl_html, "html.parser")
                        for dl_a in dl_soup.find_all("a", href=True):
                            dl_href = dl_a.get("href", "")
                            if re.search(r"\.(txt|zip|rar)", dl_href, re.I):
                                return urljoin(dl_url, dl_href)
        for a in soup.find_all("a", href=True):
            text = a.get_text().strip()
            href = a["href"]
            if any(kw in text for kw in ["下载", "TXT", "txt", "全本"]) and not href.startswith("javascript"):
                if re.search(r"\.(txt|zip|rar)", href, re.I):
                    return urljoin(novel_url, href)
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class MoreDownloadHandler(BaseSiteHandler):
    """更多有直接下载按钮的网站处理器"""

    SITES = [
        {"name": "奇书网", "base_url": "https://www.qisuwang.com/",
         "search_url": "https://www.qisuwang.com/?s={keyword}",
         "result_selector": "a[href*='/bqg/'], a[href*='/book/']"},
        {"name": "铅笔小说", "base_url": "https://www.23qb.com/",
         "search_url": "https://www.23qb.com/search.html?searchkey={keyword}",
         "result_selector": "a[href*='/book/'], h3 a"},
        {"name": "sjwx", "base_url": "http://www.sjwx.info/",
         "search_url": "http://www.sjwx.info/search.php?searchkey={keyword}",
         "result_selector": "a[href*='/book/'], a[href*='/txt/']"},
        {"name": "sjtxt", "base_url": "http://www.sjtxt.com/",
         "search_url": "http://www.sjtxt.com/search.php?searchkey={keyword}",
         "result_selector": "a[href*='/book/'], a[href*='/novel/']"},
        {"name": "17K下载", "base_url": "https://zhuanti.17k.com/",
         "search_url": "http://search.17k.com/search.xhtml?c.q={keyword}&c.st=0",
         "result_selector": "a[href*='/book/'], .result-list a"},
        {"name": "bookshuku", "base_url": "http://www.bookshuku.info/",
         "search_url": "http://www.bookshuku.info/search.asp?keyword={keyword}",
         "result_selector": "a[href*='/bookinfo/']"},
        {"name": "爱下电子书baimin", "base_url": "http://www.baimin.com/",
         "search_url": "http://www.baimin.com/search.asp?keyword={keyword}",
         "result_selector": "a[href*='/book/'], a[href*='/detail/']"},
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
        results = []
        seen = set()
        for site in self.SITES:
            page = 1
            max_page = 50
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
                selectors = site.get("result_selector", "").split(", ")
                for sel in selectors:
                    for a in soup.select(sel):
                        t = self.clean_html(a.get_text())
                        h = a.get("href", "")
                        if t and h and 3 < len(t) < 80 and not h.startswith("javascript") and t not in seen:
                            seen.add(t)
                            full_url = urljoin(site["base_url"], h)
                            results.append(SearchResult(title=t, url=full_url, source=site["name"]))
                            page_results += 1
                if page_results == 0:
                    for a in soup.find_all("a", href=True):
                        t = self.clean_html(a.get_text())
                        h = a.get("href", "")
                        if keyword in t and 3 < len(t) < 60 and not h.startswith("javascript") and t not in seen:
                            seen.add(t)
                            full_url = urljoin(site["base_url"], h)
                            results.append(SearchResult(title=t, url=full_url, source=site["name"]))
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
        intro = ""
        title_tag = soup.select_one("h1, h2, .bookname h1, .title h1, #info h1")
        if title_tag:
            title = self.clean_html(title_tag.get_text())
        for el in soup.select(".author, #info p, .info span, .meta"):
            text = self.clean_html(el.get_text())
            if "作者" in text:
                author = re.sub(r'^.*(?:作者|author)[：:\s]*', '', text).strip()
                break
        intro_tag = soup.select_one(".intro, #intro, .description, .bookintro, .excerpt")
        if intro_tag:
            intro = self.clean_html(intro_tag.get_text())[:500]
        return {"title": title, "author": author, "intro": intro, "url": url}

    async def get_download_url(self, novel_url: str) -> Optional[str]:
        html = await self._fetch(novel_url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for sel in [".download a", ".btn-down a", ".down-btn a", ".book-down a", "[class*=download] a", "[class*=down] a"]:
            for a in soup.select(sel):
                href = a.get("href", "")
                if href and not href.startswith("javascript"):
                    return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text().strip()
            if re.search(r"\.(txt|zip|rar)", href, re.I) and any(kw in text for kw in ["下载", "TXT", "全本"]):
                return urljoin(novel_url, href)
        for a in soup.find_all("a", href=True):
            if any(kw in a.get_text() for kw in ["TXT下载", "全文下载", "全本下载", "下载本书"]):
                return urljoin(novel_url, a["href"])
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
