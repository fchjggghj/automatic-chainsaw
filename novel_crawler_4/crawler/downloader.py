"""
下载管理器 — 支持断点续传、完整性验证、并发下载
"""
import os
import re
import time
import hashlib
import asyncio
import aiohttp
import aiofiles
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable
from urllib.parse import urlparse, unquote


@dataclass
class DownloadTask:
    """下载任务"""
    url: str
    filename: str
    save_dir: Path
    file_size: int = 0
    downloaded: int = 0
    status: str = "pending"  # pending / downloading / completed / failed
    error: str = ""
    retries: int = 0
    max_retries: int = 3
    start_time: float = 0
    checksum: str = ""


@dataclass
class DownloadProgress:
    """下载进度"""
    tasks: list[DownloadTask] = field(default_factory=list)
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0


class DownloadManager:
    """异步下载管理器"""

    def __init__(
        self,
        output_dir: Path,
        max_concurrent: int = 3,
        timeout: int = 30,
        proxy: Optional[str] = None,
        max_file_size: int = 50 * 1024 * 1024,
        verify_sample_bytes: int = 50000,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.proxy = proxy
        self.max_file_size = max_file_size
        self.verify_sample_bytes = verify_sample_bytes

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None
        self.progress = DownloadProgress()
        self.on_progress: Optional[Callable] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            conn = aiohttp.TCPConnector(limit=self.max_concurrent, force_close=True)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=conn, timeout=timeout,
                headers={"User-Agent": self._random_ua()}
            )
        return self._session

    def _random_ua(self) -> str:
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        ]
        import random
        return random.choice(agents)

    def _sanitize_filename(self, name: str) -> str:
        """净化文件名"""
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        return name[:200]

    def _extract_filename(self, url: str, response: aiohttp.ClientResponse) -> str:
        """从URL或响应头提取文件名"""
        cd = response.headers.get("Content-Disposition", "")
        if cd:
            m = re.search(r'filename[*]?=["\']?([^"\';]+)', cd)
            if m:
                return unquote(m.group(1))
        path = urlparse(url).path
        name = unquote(Path(path).name)
        if name and '.' in name:
            return name
        return f"download_{int(time.time())}.txt"

    async def download(
        self,
        url: str,
        filename: str = "",
        verify_regex: Optional[str] = None,
    ) -> Optional[Path]:
        """
        下载文件，返回保存路径或None
        """
        task = DownloadTask(url=url, filename=filename, save_dir=self.output_dir)
        self.progress.tasks.append(task)
        self.progress.total_count += 1

        async with self._semaphore:
            for attempt in range(task.max_retries):
                try:
                    result = await self._do_download(task, verify_regex)
                    if result:
                        task.status = "completed"
                        self.progress.completed_count += 1
                        if self.on_progress:
                            self.on_progress(self.progress)
                        return result
                except Exception as e:
                    task.error = str(e)
                    if attempt < task.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)

            task.status = "failed"
            self.progress.failed_count += 1
            if self.on_progress:
                self.on_progress(self.progress)
            return None

    async def _do_download(
        self,
        task: DownloadTask,
        verify_regex: Optional[str] = None,
    ) -> Optional[Path]:
        session = await self._get_session()

        async with session.get(task.url) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")

            task.file_size = int(resp.headers.get("Content-Length", 0))
            if task.file_size > self.max_file_size:
                raise Exception(f"文件过大: {task.file_size / 1024 / 1024:.1f}MB > {self.max_file_size / 1024 / 1024:.0f}MB")

            if not task.filename:
                task.filename = self._extract_filename(task.url, resp)

            safe_name = self._sanitize_filename(task.filename)
            filepath = self.output_dir / safe_name

            task.status = "downloading"
            task.start_time = time.time()

            # 断点续传
            temp_path = filepath.with_suffix(filepath.suffix + ".part")
            if temp_path.exists():
                task.downloaded = temp_path.stat().st_size
            else:
                task.downloaded = 0

            # 流式写入
            async with aiofiles.open(temp_path, "ab" if task.downloaded else "wb") as f:
                chunk_size = 64 * 1024
                async for chunk in resp.content.iter_chunked(chunk_size):
                    await f.write(chunk)
                    task.downloaded += len(chunk)
                    if self.on_progress:
                        self.progress.downloaded_bytes += len(chunk)
                        self.on_progress(self.progress)

            # 验证
            if verify_regex:
                try:
                    async with aiofiles.open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
                        sample = await f.read(self.verify_sample_bytes)
                    if not re.search(verify_regex, sample):
                        temp_path.unlink(missing_ok=True)
                        raise Exception("内容验证失败：不匹配目标类型")
                except UnicodeDecodeError:
                    pass

            # 完成
            temp_path.rename(filepath)
            task.checksum = self._file_md5(filepath)

            if self.on_progress:
                self.on_progress(self.progress)

            return filepath

    def _file_md5(self, path: Path) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def get_progress(self) -> dict:
        p = self.progress
        return {
            "total": p.total_count,
            "completed": p.completed_count,
            "failed": p.failed_count,
            "pending": p.total_count - p.completed_count - p.failed_count,
            "total_bytes": p.total_bytes,
            "downloaded_bytes": p.downloaded_bytes,
            "tasks": [
                {
                    "filename": t.filename,
                    "status": t.status,
                    "url": t.url[:80],
                    "error": t.error[:120],
                }
                for t in p.tasks[-20:]
            ],
        }
