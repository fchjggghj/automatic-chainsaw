"""
去重管理器 — 扫描整个下载目录，智能去重和替换
核心逻辑：
  1. 扫描整个downloads目录建立已有书籍索引（书名→章节数映射）
  2. 新下载前，检查是否已有同名书籍
  3. 如果已有，比较章节数：
     - 新版本章节更多 → 替换旧版本
     - 新版本章节更少或相同 → 放弃下载
  4. 如果没有，正常下载
"""
import re
import os
from pathlib import Path
from typing import Optional


class DedupManager:
    """去重管理器"""

    def __init__(self, download_dir: Path):
        self.download_dir = Path(download_dir)
        self._index: dict[str, dict] = {}
        self._built = False

    def build_index(self, force: bool = False):
        """扫描整个下载目录，建立书名→章节数索引"""
        if self._built and not force:
            return

        if not self.download_dir.exists():
            self._built = True
            return

        count = 0
        for root, dirs, files in os.walk(self.download_dir):
            for f in files:
                fp = Path(root) / f
                if fp.suffix.lower() not in ('.txt', '.zip', '.rar'):
                    continue

                name = fp.stem
                if '_dup_' in name:
                    name = name.split('_dup_')[0]

                title, chapters = self._parse_filename(name)
                if title:
                    norm_title = self._normalize_title(title)
                    size = fp.stat().st_size
                    info = {
                        'filepath': str(fp),
                        'chapters': chapters,
                        'title': title,
                        'size': size,
                    }
                    # 保留章节数最多的，章节数相同保留文件最大的
                    if norm_title in self._index:
                        existing = self._index[norm_title]
                        if chapters > existing.get('chapters', 0):
                            self._index[norm_title] = info
                        elif chapters == existing.get('chapters', 0) and size > existing.get('size', 0):
                            self._index[norm_title] = info
                    else:
                        self._index[norm_title] = info
                    count += 1

        self._built = True
        return count

    def add_to_index(self, filepath: Path, chapters: int = 0):
        """下载完成后添加到索引"""
        if not self._built:
            self.build_index()

        name = filepath.stem
        if '_dup_' in name:
            name = name.split('_dup_')[0]

        title, file_chapters = self._parse_filename(name)
        if chapters == 0:
            chapters = file_chapters

        if title:
            norm_title = self._normalize_title(title)
            size = filepath.stat().st_size if filepath.exists() else 0
            info = {
                'filepath': str(filepath),
                'chapters': chapters,
                'title': title,
                'size': size,
            }
            if norm_title in self._index:
                existing = self._index[norm_title]
                if chapters > existing.get('chapters', 0):
                    self._index[norm_title] = info
                elif chapters == existing.get('chapters', 0) and size > existing.get('size', 0):
                    self._index[norm_title] = info
            else:
                self._index[norm_title] = info

    def _parse_filename(self, stem: str) -> tuple[str, int]:
        """
        解析文件名，提取书名和章节数。
        支持多种格式。
        """
        chapters = 0
        title = stem

        m = re.search(r'【(\d+)到(\d+)章】', stem)
        if m:
            start_ch = int(m.group(1))
            end_ch = int(m.group(2))
            chapters = end_ch - start_ch + 1
            title_m = re.match(r'\d+_(.+?)【', stem)
            if title_m:
                title = title_m.group(1)
            return title, chapters

        m = re.search(r'(\d+)[\-~到至](\d+)章', stem)
        if m:
            start_ch = int(m.group(1))
            end_ch = int(m.group(2))
            chapters = end_ch - start_ch + 1
            title_m = re.match(r'\d+_(.+?)[\[\[【\(（]', stem)
            if title_m:
                title = title_m.group(1)
            return title, chapters

        m = re.match(r'(.+?)_\d{8}$', stem)
        if m:
            parts = stem.rsplit('_', 2)
            if len(parts) >= 3 and re.match(r'\d{8}$', parts[-1]):
                title = parts[0]
            elif len(parts) >= 2 and re.match(r'\d{8}$', parts[-1]):
                title = parts[0]
            return title, 0

        m = re.match(r'\d+_(.+)', stem)
        if m:
            title = m.group(1)

        return title, 0

    def _normalize_title(self, title: str) -> str:
        """规范化书名用于匹配（去空格、标点、统一符号）"""
        t = re.sub(r'[\[【\(（\[].*?[\]】\)）\]]', '', title)
        t = re.sub(r'[\s\u3000，,。.、：:；;！!？?·…—\-_\d]', '', t)
        t = t.lower()
        return t

    def check_duplicate(self, title: str) -> Optional[dict]:
        """检查书名是否已存在。返回 None 表示不存在；返回 dict 表示已存在。"""
        if not self._built:
            self.build_index()

        norm_title = self._normalize_title(title)

        if norm_title in self._index:
            info = self._index[norm_title]
            if info.get('chapters', 0) == 0:
                filepath = Path(info['filepath'])
                if filepath.exists():
                    ch = self.count_chapters_in_file(filepath)
                    if ch > 0:
                        info['chapters'] = ch
            return info

        for key, info in self._index.items():
            if norm_title in key or key in norm_title:
                min_len = min(len(norm_title), len(key))
                if min_len > 0:
                    overlap = sum(1 for c in norm_title if c in key)
                    if overlap / max(len(key), 1) > 0.6:
                        if info.get('chapters', 0) == 0:
                            filepath = Path(info['filepath'])
                            if filepath.exists():
                                ch = self.count_chapters_in_file(filepath)
                                if ch > 0:
                                    info['chapters'] = ch
                        return info

        return None

    def should_download(self, title: str, new_chapters: int = 0) -> tuple[bool, str, Optional[dict]]:
        """
        判断是否应该下载。
        返回: (是否下载, 原因, 已有文件信息)
        """
        existing = self.check_duplicate(title)
        if not existing:
            return True, "新书，不存在", None

        existing_chapters = existing.get('chapters', 0)

        if new_chapters == 0 and existing_chapters == 0:
            return True, "已存在但章节数未知，下载后验证", existing

        if new_chapters == 0:
            return False, f"已存在（{existing_chapters}章），跳过", existing

        if new_chapters > existing_chapters:
            return True, f"已存在（{existing_chapters}章），新版本更多（{new_chapters}章），替换", existing

        return False, f"已存在（{existing_chapters}章），新版本不更多（{new_chapters}章），跳过", existing

    def replace_file(self, old_info: dict, new_filepath: Path) -> bool:
        """用新文件替换旧文件"""
        try:
            old_path = Path(old_info['filepath'])
            if old_path.exists():
                old_path.unlink()

            target = old_path.parent / new_filepath.name
            if target.exists() and target != new_filepath:
                target.unlink()

            import shutil
            if new_filepath.exists():
                shutil.move(str(new_filepath), str(target))
            else:
                target = new_filepath

            norm_title = self._normalize_title(old_info.get('title', ''))
            if norm_title in self._index:
                self._index[norm_title] = {
                    'filepath': str(target),
                    'chapters': old_info.get('chapters', 0),
                    'title': old_info.get('title', ''),
                    'size': target.stat().st_size if target.exists() else 0,
                }
            return True
        except Exception as e:
            pass
        return False

    def count_files(self) -> int:
        """统计目录中的文件数"""
        if not self.download_dir.exists():
            return 0
        count = 0
        for root, dirs, files in os.walk(self.download_dir):
            for f in files:
                if f.endswith(('.txt', '.zip', '.rar')):
                    count += 1
        return count

    def get_stats(self) -> dict:
        """获取统计信息"""
        self.build_index()
        return {
            "total_files": self.count_files(),
            "indexed_titles": len(self._index),
            "titles_with_chapters": sum(1 for v in self._index.values() if v.get('chapters', 0) > 0),
        }

    @staticmethod
    def count_chapters_in_file(filepath: Path, sample_bytes: int = 500000) -> int:
        """通过读取文件内容来统计章节数（默认读前500KB）"""
        try:
            chapter_patterns = [
                r'^第[一二三四五六七八九十百千零\d]+章',
                r'^Chapter\s+\d+',
                r'^\d+[\.\、]',
                r'^第[一二三四五六七八九十百千零\d]+节',
                r'^第[一二三四五六七八九十百千零\d]+卷',
            ]
            compiled = [re.compile(p) for p in chapter_patterns]
            count = 0
            read_bytes = 0
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    for pat in compiled:
                        if pat.match(line):
                            count += 1
                            break
                    read_bytes += len(line.encode('utf-8', errors='ignore'))
                    if read_bytes > sample_bytes and count > 0:
                        file_size = filepath.stat().st_size
                        if file_size > sample_bytes and read_bytes > 0:
                            ratio = file_size / read_bytes
                            estimated = int(count * ratio)
                            return max(count, estimated)
                        break
            return count
        except Exception:
            return 0
