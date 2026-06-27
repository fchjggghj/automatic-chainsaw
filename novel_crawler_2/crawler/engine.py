"""
爬虫调度引擎 — 严格串行搜索下载 + 去重 + 重试 + 状态跟踪

核心流程：
  关键词 → 站点1(搜索→逐一串行下载) → 站点2(搜索→逐一串行下载) → ...

串行保证：
  - 每个站点内，搜索结果逐一下载，前一本完成后才开始下一本
  - 每个站点处理完，才切换到下一个站点
  - 禁止任何并发下载操作
"""
import asyncio
import time
import json
import re
import logging
from pathlib import Path
from typing import Optional, Callable
from enum import Enum

from .filter import NovelFilter, create_filter
from .downloader import DownloadManager
from .storage import HistoryDB, StorageManager, DownloadRecord
from .dedup import DedupManager
from .site_handlers.base import SearchResult
from .site_handlers.generic import GenericHandler, SiteConfig
from .site_handlers.biquge_handler import BiqugeHandler
from .site_handlers.txt_download_handler import TxtDownloadHandler
from .site_handlers.dedicated_handlers import (
    ZhixuanHandler,
    EmpireCmsHandler,
    NovelessHandler,
    HaodooHandler,
    Txt8Handler,
    BookdownHandler,
    CustomSearchHandler,
    XmsoushuHandler,
    Ixdzs8Handler,
    MoreDownloadHandler,
)

log = logging.getLogger("crawler_engine")


# ─── 状态跟踪 ───

class TaskStatus(str, Enum):
    PENDING = "pending"
    SEARCHING = "searching"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class NovelTask:
    """单本小说的下载任务状态"""

    def __init__(self, title: str, source: str, url: str = "", download_url: str = ""):
        self.title = title
        self.source = source
        self.url = url
        self.download_url = download_url
        self.author = ""
        self.intro = ""
        self.category = "快穿"
        self.match_method = ""
        self.match_detail = ""
        self.status = TaskStatus.PENDING
        self.error = ""
        self.filepath = ""
        self.file_size = 0
        self.retry_count = 0
        self.max_retries = 3
        self.started_at = ""
        self.completed_at = ""
        self.dedup_action = ""  # "" / "new" / "replaced" / "skipped_dedup"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "download_url": self.download_url,
            "author": self.author,
            "status": self.status.value,
            "error": self.error,
            "filepath": self.filepath,
            "file_size": self.file_size,
            "retry_count": self.retry_count,
            "dedup_action": self.dedup_action,
            "match_method": self.match_method,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class CrawlerEngine:
    """爬虫调度引擎 — 严格串行模式"""

    # ─── 初始化 ───

    def __init__(
        self,
        config_path: Optional[Path] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.on_log = on_log or print
        self.config = self._load_config(config_path)

        cfg = self.config
        base_dir = Path(__file__).parent.parent
        self.output_dir = base_dir / cfg.get("download", {}).get("output_dir", "downloads")

        self.history = HistoryDB(base_dir / "history.db")
        self.storage = StorageManager(
            self.output_dir,
            cfg.get("download", {}).get("organize_by", "category")
        )
        self.dedup = DedupManager(self.output_dir)
        self.filter = create_filter(config_path)
        self.downloader: Optional[DownloadManager] = None

        self._search_keywords = cfg.get("search", {}).get("keywords", ["快穿"])
        self._max_pages = cfg.get("search", {}).get("max_pages", 5)
        self._results_per_site = cfg.get("search", {}).get("results_per_site", 20)
        self._crawl_delay = cfg.get("crawler", {}).get("request_delay", 1.5)
        self._max_concurrent = cfg.get("crawler", {}).get("concurrency", 1)  # 串行=1
        self._timeout = cfg.get("crawler", {}).get("timeout", 30)
        self._max_retries = cfg.get("crawler", {}).get("retry_count", 3)

        self._handlers = []
        self._running = False
        self._cancelled = False

        # 详细的任务级状态跟踪
        self._tasks: list[NovelTask] = []
        self._stats = {
            "searched": 0,
            "filtered": 0,
            "downloaded": 0,
            "failed": 0,
            "skipped": 0,
            "replaced": 0,
        }
        self._current_site = ""
        self._current_keyword = ""
        self._current_novel = ""

    def _load_config(self, config_path: Optional[Path]) -> dict:
        if config_path and config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    # ─── Handler 初始化 ───

    async def _init_handlers(self):
        """初始化站点处理器"""
        self._handlers = []

        handler_configs = [
            (Ixdzs8Handler, "爱下电子书", "https://ixdzs8.com/"),
            (ZhixuanHandler, "知轩藏书", "http://zxcs.me/"),
            (EmpireCmsHandler, "帝国CMS系", ""),
            (NovelessHandler, "精校全本", "https://noveless.com/"),
            (HaodooHandler, "好读", "https://www.haodoo.net/"),
            (Txt8Handler, "小说下载吧", "http://www.txt8.net/"),
            (BookdownHandler, "TXT图书下载网", "http://www.bookdown.com.cn/"),
            (MoreDownloadHandler, "更多下载站", ""),
            (BiqugeHandler, "笔趣阁系", ""),
            (TxtDownloadHandler, "TXT下载站", ""),
            (CustomSearchHandler, "自定义搜索", ""),
            (XmsoushuHandler, "熊猫搜书", "https://xmsoushu.com/"),
            (GenericHandler, "通用搜索", ""),
        ]

        for cls, name, url in handler_configs:
            self._handlers.append(cls(
                SiteConfig(name=name, base_url=url),
                timeout=self._timeout, delay=self._crawl_delay,
            ))

    # ─── 核心流程：串行搜索下载 ───

    async def run(
        self,
        keywords: Optional[list[str]] = None,
        auto_download: bool = True,
        site_names: Optional[list[str]] = None,
    ) -> dict:
        """
        完整串行流程：关键词 → 逐站点搜索 → 逐本下载

        Args:
            keywords: 搜索关键词列表
            auto_download: 是否自动下载
            site_names: 指定站点名称列表（None=全部站点）
        """
        if keywords is None:
            keywords = self._search_keywords

        self._running = True
        self._cancelled = False
        self._tasks = []
        self._stats = {
            "searched": 0,
            "filtered": 0,
            "downloaded": 0,
            "failed": 0,
            "skipped": 0,
            "replaced": 0,
        }

        await self._init_handlers()

        # 构建去重复文件夹索引
        self._log("=" * 60)
        self._log("智能小说爬虫启动（串行模式）")
        self._log("=" * 60)
        self._log("[去重] 扫描去重复文件夹...")
        self.dedup.build_index()
        dedup_stats = self.dedup.get_stats()
        self._log(f"[去重] 已索引 {dedup_stats['indexed_titles']} 本书（共 {dedup_stats['total_files']} 个文件）")

        # 初始化下载器
        dl_cfg = self.config.get("download", {})
        self.downloader = DownloadManager(
            output_dir=self.output_dir,
            max_concurrent=1,  # 严格串行
            timeout=self._timeout,
            max_file_size=dl_cfg.get("max_file_size_mb", 50) * 1024 * 1024,
            verify_sample_bytes=dl_cfg.get("verify_sample_bytes", 50000),
        )

        verify_regex = self.config.get("search", {}).get("regex_filter", {}).get("all_combined", "")

        # 过滤要执行的handler
        handlers = self._handlers
        if site_names:
            handlers = [h for h in self._handlers if h.config.name in site_names]
            self._log(f"[过滤] 指定站点: {[h.config.name for h in handlers]}")

        # ─── 逐关键词、逐站点、串行搜索+下载 ───
        for kw in keywords:
            if self._cancelled:
                self._log("[取消] 用户取消操作")
                break
            self._current_keyword = kw
            self._log(f"\n{'─' * 50}")
            self._log(f"[关键词] {kw}")
            self._log(f"{'─' * 50}")

            for handler in handlers:
                if self._cancelled:
                    break

                site_name = handler.config.name
                self._current_site = site_name
                self._log(f"\n[站点] {site_name} — 开始搜索 '{kw}'")

                # ── 1. 搜索 ──
                raw_results: list[SearchResult] = []
                try:
                    raw_results = await handler.search(kw, self._results_per_site)
                    self._stats["searched"] += len(raw_results)
                    self._log(f"  搜索返回 {len(raw_results)} 条结果")
                except Exception as e:
                    self._log(f"  搜索失败: {e}")
                    await asyncio.sleep(self._crawl_delay)
                    continue

                if not raw_results:
                    self._log(f"  无结果，跳过此站点")
                    await asyncio.sleep(self._crawl_delay)
                    continue

                # ── 2. 逐条过滤 + 串行下载 ──
                seen_titles = set()
                for idx, r in enumerate(raw_results, 1):
                    if self._cancelled:
                        break

                    # 跨站点去重
                    norm_title = re.sub(r'[\s\u3000，,。.、：:；;！!？?·…—\-_\d]', '', r.title).lower()
                    if norm_title in seen_titles:
                        continue
                    seen_titles.add(norm_title)

                    self._current_novel = r.title

                    # 创建任务对象
                    task = NovelTask(
                        title=r.title,
                        source=r.source or site_name,
                        url=r.url,
                        download_url=r.download_url,
                    )
                    task.author = r.author
                    task.intro = r.intro or ""
                    task.started_at = time.strftime("%Y-%m-%d %H:%M:%S")

                    # 过滤检查
                    is_match, method, detail = self.filter.is_kuai_chuan(
                        title=r.title, intro=r.intro
                    )

                    # 如果书名和简介都没匹配，尝试获取简介再判断
                    if not is_match and r.url:
                        try:
                            info = await handler.get_novel_info(r.url)
                            if info and info.get("intro"):
                                is_match, method, detail = self.filter.is_kuai_chuan(
                                    title=r.title, intro=info["intro"]
                                )
                                if is_match:
                                    task.intro = info["intro"][:500]
                            await asyncio.sleep(self._crawl_delay)
                        except Exception:
                            pass

                    if not is_match:
                        task.status = TaskStatus.SKIPPED
                        task.error = "不匹配过滤条件"
                        self._tasks.append(task)
                        continue

                    self._stats["filtered"] += 1
                    task.match_method = method
                    task.match_detail = detail
                    task.category = r.category or "快穿"

                    if not auto_download:
                        task.status = TaskStatus.COMPLETED
                        self._tasks.append(task)
                        continue

                    # ── 3. 去重检查 ──
                    should_dl, dedup_reason, existing = self.dedup.should_download(r.title)
                    if not should_dl:
                        task.status = TaskStatus.SKIPPED
                        task.error = dedup_reason
                        task.dedup_action = "skipped_dedup"
                        self._stats["skipped"] += 1
                        self._log(f"  [{idx}/{len(raw_results)}] 跳过 {r.title}: {dedup_reason}")
                        self._tasks.append(task)
                        continue

                    # ── 4. 获取下载链接（如果没有直链）──
                    download_url = r.download_url
                    if not download_url and r.url:
                        self._log(f"  [{idx}/{len(raw_results)}] 获取下载链接: {r.title}")
                        try:
                            download_url = await handler.get_download_url(r.url)
                            if not download_url:
                                # 尝试其他handler
                                for alt_handler in self._handlers:
                                    if alt_handler is handler:
                                        continue
                                    try:
                                        download_url = await alt_handler.get_download_url(r.url)
                                        if download_url:
                                            break
                                    except Exception:
                                        continue
                        except Exception as e:
                            self._log(f"  获取下载链接失败: {e}")

                        if not download_url:
                            task.status = TaskStatus.FAILED
                            task.error = "无法获取下载链接"
                            self._stats["failed"] += 1
                            self._log(f"  [{idx}/{len(raw_results)}] 无下载链接: {r.title}")
                            self._tasks.append(task)
                            continue

                        task.download_url = download_url

                    # URL级去重
                    if self.history.is_duplicate(download_url):
                        task.status = TaskStatus.SKIPPED
                        task.error = "已下载过（URL重复）"
                        self._stats["skipped"] += 1
                        self._log(f"  [{idx}/{len(raw_results)}] 跳过 {r.title}: 已下载过")
                        self._tasks.append(task)
                        continue

                    # ── 5. 串行下载（带重试）──
                    self._log(f"  [{idx}/{len(raw_results)}] 下载: {r.title}")
                    if existing:
                        task.dedup_action = "replaced"
                        self._log(f"    替换模式: {dedup_reason}")
                    else:
                        task.dedup_action = "new"

                    dl_success = False
                    for attempt in range(1, self._max_retries + 1):
                        if self._cancelled:
                            break
                        task.retry_count = attempt
                        task.status = TaskStatus.DOWNLOADING

                        try:
                            filename = self._make_filename(r.title, r.author)
                            result_path = await self.downloader.download(
                                url=download_url,
                                filename=filename,
                                verify_regex=verify_regex or None,
                            )

                            if result_path:
                                # 下载成功 → 去重替换验证
                                dl_success = await self._handle_download_result(
                                    result_path, task, existing
                                )
                                if dl_success:
                                    break
                            else:
                                self._log(f"    重试 {attempt}/{self._max_retries}: 下载返回空")
                                if attempt < self._max_retries:
                                    await asyncio.sleep(2 ** attempt)
                        except Exception as e:
                            self._log(f"    重试 {attempt}/{self._max_retries}: {e}")
                            task.error = str(e)[:200]
                            if attempt < self._max_retries:
                                await asyncio.sleep(2 ** attempt)

                    if not dl_success and not self._cancelled:
                        task.status = TaskStatus.FAILED
                        self._stats["failed"] += 1
                        self._log(f"  ✗ {r.title}: 下载失败（已重试{task.retry_count}次）")
                        self.history.update_status(
                            self.history.add_record(DownloadRecord(
                                title=r.title, author=r.author,
                                url=download_url, category=task.category,
                                site_name=r.source or site_name,
                                match_method=method, match_detail=detail,
                            )), "failed"
                        )

                    self._tasks.append(task)
                    # 下载间隔
                    await asyncio.sleep(self._crawl_delay)

                # 站点间间隔
                self._log(f"  {site_name} 处理完毕")
                await asyncio.sleep(self._crawl_delay)

        # ─── 清理 ───
        self._current_site = ""
        self._current_keyword = ""
        self._current_novel = ""

        # 关闭下载器
        if self.downloader:
            await self.downloader.close()
            self.downloader = None

        # 关闭所有 handler 的 session
        for handler in self._handlers:
            if hasattr(handler, 'close') and callable(handler.close):
                try:
                    await handler.close()
                except Exception:
                    pass

        self._running = False

        # 汇总
        self._log(f"\n{'=' * 60}")
        self._log(f"[汇总] 搜索{self._stats['searched']} | 过滤{self._stats['filtered']} | "
                   f"下载{self._stats['downloaded']} | 失败{self._stats['failed']} | "
                   f"跳过{self._stats['skipped']} | 替换{self._stats['replaced']}")
        self._log(f"{'=' * 60}")

        return self._stats

    # ─── 下载结果处理（去重替换）───

    async def _handle_download_result(
        self,
        result_path: Path,
        task: NovelTask,
        existing_dedup: Optional[dict],
    ) -> bool:
        """处理下载成功的文件，含去重替换逻辑。返回True=成功处理"""
        try:
            # 如果有去重复文件夹的旧版本需要比较
            if existing_dedup:
                new_chapters = DedupManager.count_chapters_in_file(result_path)
                old_chapters = existing_dedup.get('chapters', 0)

                # 旧版本章节数为0时，尝试从文件内容统计
                if old_chapters == 0:
                    old_path = Path(existing_dedup['filepath'])
                    if old_path.exists():
                        old_chapters = DedupManager.count_chapters_in_file(old_path)
                        existing_dedup['chapters'] = old_chapters

                if old_chapters > 0 and new_chapters > 0 and new_chapters <= old_chapters:
                    # 新版本不比旧版多，删除刚下载的文件
                    self._log(f"    替换取消: 新({new_chapters}章) ≤ 旧({old_chapters}章)")
                    result_path.unlink(missing_ok=True)
                    task.status = TaskStatus.SKIPPED
                    task.error = f"已有更全版本({old_chapters}章 > {new_chapters}章)"
                    task.dedup_action = "skipped_dedup"
                    self._stats["skipped"] += 1
                    return True

                # 新版本章节更多，执行替换
                if new_chapters > old_chapters:
                    replaced = self.dedup.replace_file(existing_dedup, result_path)
                    if replaced:
                        task.status = TaskStatus.COMPLETED
                        task.filepath = str(self.dedup.dedup_dir / result_path.name)
                        task.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
                        self._stats["downloaded"] += 1
                        self._stats["replaced"] += 1
                        self._log(f"  ✓ 替换成功: {task.title} 旧({old_chapters}章)→新({new_chapters}章)")
                        self.history.update_status(
                            self.history.add_record(DownloadRecord(
                                title=task.title, author=task.author,
                                url=task.download_url, category=task.category,
                                site_name=task.source,
                                match_method=task.match_method,
                                match_detail=task.match_detail,
                            )), "completed",
                            filepath=task.filepath,
                            file_size=0,
                        )
                        return True

            # 普通下载（无替换）
            task.status = TaskStatus.COMPLETED
            task.filepath = str(result_path)
            task.file_size = result_path.stat().st_size
            task.completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self._stats["downloaded"] += 1
            self._log(f"  ✓ 下载完成: {task.title} → {result_path.name}")

            # 归档
            try:
                self.storage.organize(
                    result_path,
                    category=task.category,
                    author=task.author,
                    site=task.source,
                )
            except Exception:
                pass

            self.history.update_status(
                self.history.add_record(DownloadRecord(
                    title=task.title, author=task.author,
                    url=task.download_url, category=task.category,
                    site_name=task.source,
                    match_method=task.match_method,
                    match_detail=task.match_detail,
                )), "completed",
                filepath=task.filepath,
                file_size=task.file_size,
            )
            return True

        except Exception as e:
            self._log(f"    处理下载结果异常: {e}")
            return False

    # ─── 辅助方法 ───

    @staticmethod
    def _make_filename(title: str, author: str) -> str:
        """生成安全的文件名"""
        name = f"{title}_{author}" if author else title
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        return name[:200] + ".txt"

    def cancel(self):
        """取消当前运行的任务"""
        self._cancelled = True
        self._running = False
        self._log("[取消] 正在停止...")

    # ─── 状态查询 API ───

    def get_results(self) -> list[dict]:
        """获取所有任务状态"""
        return [t.to_dict() for t in self._tasks]

    def get_progress(self) -> dict:
        """获取实时进度"""
        total = len(self._tasks)
        completed = sum(1 for t in self._tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self._tasks if t.status == TaskStatus.FAILED)
        skipped = sum(1 for t in self._tasks if t.status == TaskStatus.SKIPPED)
        downloading = sum(1 for t in self._tasks if t.status == TaskStatus.DOWNLOADING)
        pending = sum(1 for t in self._tasks if t.status == TaskStatus.PENDING)

        return {
            "running": self._running,
            "cancelled": self._cancelled,
            "current_keyword": self._current_keyword,
            "current_site": self._current_site,
            "current_novel": self._current_novel,
            "stats": self._stats,
            "tasks": {
                "total": total,
                "completed": completed,
                "failed": failed,
                "skipped": skipped,
                "downloading": downloading,
                "pending": pending,
            },
            "downloads": self.downloader.get_progress() if self.downloader else {},
        }

    def get_stats(self) -> dict:
        return dict(self._stats)

    # ─── 仅搜索（不下载）───

    async def search(self, keywords: Optional[list[str]] = None) -> list[dict]:
        """仅搜索，不下载。返回过滤后的结果列表"""
        return (await self.run(keywords, auto_download=False, site_names=None), self._tasks)

    async def get_download_url(self, novel_url: str) -> Optional[str]:
        """获取小说的下载链接"""
        if not self._handlers:
            await self._init_handlers()
        for handler in self._handlers:
            try:
                dl_url = await handler.get_download_url(novel_url)
                if dl_url:
                    return dl_url
            except Exception:
                continue
        return None

    async def download_selected(self, results: list[dict]):
        """批量下载选中的搜索结果"""
        self._running = True
        self._cancelled = False
        self._tasks = []
        self._stats = {
            "searched": 0,
            "filtered": 0,
            "downloaded": 0,
            "failed": 0,
            "skipped": 0,
            "replaced": 0,
        }

        await self._init_handlers()

        # 构建去重索引
        self._log("[下载] 扫描去重复文件夹...")
        self.dedup.build_index()

        # 初始化下载器
        dl_cfg = self.config.get("download", {})
        self.downloader = DownloadManager(
            output_dir=self.output_dir,
            max_concurrent=1,
            timeout=self._timeout,
            max_file_size=dl_cfg.get("max_file_size_mb", 50) * 1024 * 1024,
            verify_sample_bytes=dl_cfg.get("verify_sample_bytes", 50000),
        )

        verify_regex = self.config.get("search", {}).get("regex_filter", {}).get("all_combined", "")

        for idx, item in enumerate(results, 1):
            if self._cancelled:
                self._log("[取消] 用户取消操作")
                break

            title = item.get("title", "")
            url = item.get("url", "")
            source = item.get("source", "")
            download_url = item.get("download_url", "")
            author = item.get("author", "")

            self._current_novel = title
            self._log(f"  [{idx}/{len(results)}] 下载: {title}")

            task = NovelTask(
                title=title, source=source, url=url, download_url=download_url
            )
            task.author = author
            task.match_method = item.get("match_method", "")
            task.match_detail = item.get("match_detail", "")
            task.category = item.get("category", "快穿")
            task.started_at = time.strftime("%Y-%m-%d %H:%M:%S")

            # 去重检查
            should_dl, dedup_reason, existing = self.dedup.should_download(title)
            if not should_dl:
                task.status = TaskStatus.SKIPPED
                task.error = dedup_reason
                task.dedup_action = "skipped_dedup"
                self._stats["skipped"] += 1
                self._log(f"  [{idx}/{len(results)}] 跳过 {title}: {dedup_reason}")
                self._tasks.append(task)
                continue

            # 获取下载链接
            if not download_url and url:
                self._log(f"  [{idx}/{len(results)}] 获取下载链接: {title}")
                try:
                    download_url = await self.get_download_url(url)
                except Exception as e:
                    self._log(f"  获取下载链接失败: {e}")

                if not download_url:
                    task.status = TaskStatus.FAILED
                    task.error = "无法获取下载链接"
                    self._stats["failed"] += 1
                    self._log(f"  [{idx}/{len(results)}] 无下载链接: {title}")
                    self._tasks.append(task)
                    continue

                task.download_url = download_url

            # URL级去重
            if self.history.is_duplicate(download_url):
                task.status = TaskStatus.SKIPPED
                task.error = "已下载过（URL重复）"
                self._stats["skipped"] += 1
                self._log(f"  [{idx}/{len(results)}] 跳过 {title}: 已下载过")
                self._tasks.append(task)
                continue

            if existing:
                task.dedup_action = "replaced"
            else:
                task.dedup_action = "new"

            # 下载（带重试）
            dl_success = False
            for attempt in range(1, self._max_retries + 1):
                if self._cancelled:
                    break
                task.retry_count = attempt
                task.status = TaskStatus.DOWNLOADING

                try:
                    filename = self._make_filename(title, author)
                    result_path = await self.downloader.download(
                        url=download_url,
                        filename=filename,
                        verify_regex=verify_regex or None,
                    )

                    if result_path:
                        dl_success = await self._handle_download_result(
                            result_path, task, existing
                        )
                        if dl_success:
                            break
                    else:
                        self._log(f"    重试 {attempt}/{self._max_retries}: 下载返回空")
                        if attempt < self._max_retries:
                            await asyncio.sleep(2 ** attempt)
                except Exception as e:
                    self._log(f"    重试 {attempt}/{self._max_retries}: {e}")
                    task.error = str(e)[:200]
                    if attempt < self._max_retries:
                        await asyncio.sleep(2 ** attempt)

            if not dl_success and not self._cancelled:
                task.status = TaskStatus.FAILED
                self._stats["failed"] += 1
                self._log(f"  ✗ {title}: 下载失败（已重试{task.retry_count}次）")
                self.history.update_status(
                    self.history.add_record(DownloadRecord(
                        title=title, author=author,
                        url=download_url, category=task.category,
                        site_name=source,
                        match_method=task.match_method, match_detail=task.match_detail,
                    )), "failed"
                )

            self._tasks.append(task)
            await asyncio.sleep(self._crawl_delay)

        # 清理
        self._current_novel = ""
        if self.downloader:
            await self.downloader.close()
            self.downloader = None
        for handler in self._handlers:
            if hasattr(handler, 'close') and callable(handler.close):
                try:
                    await handler.close()
                except Exception:
                    pass

        self._running = False
        self._log(f"[下载完成] 下载{self._stats['downloaded']} | 失败{self._stats['failed']} | 跳过{self._stats['skipped']}")

    async def download_single(self, title: str, url: str, source: str = ""):
        """下载单本小说"""
        await self.download_selected([{
            "title": title, "url": url, "source": source,
            "download_url": "", "author": "", "match_method": "",
            "match_detail": "", "category": "快穿",
        }])

    def _log(self, msg: str):
        log.info(msg)
        if self.on_log:
            self.on_log(msg)
