#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理重复小说文件 — 同一本书只保留章节最多/文件最大的版本
"""
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

DOWNLOAD_DIR = Path(r"C:\Users\Administrator\Desktop\books\books\novel_crawler\downloads")


def normalize_title(title: str) -> str:
    """规范化书名用于去重匹配"""
    t = re.sub(r'[\[【\(（\[].*?[\]】\)）\]]', '', title)
    t = re.sub(r'[\s\u3000，,。.、：:；;！!？?·…—\-_\d]', '', t)
    t = t.lower()
    return t


def count_chapters_in_file(filepath: Path, sample_bytes: int = 500000) -> int:
    """统计文件章节数"""
    try:
        chapter_patterns = [
            r'^第[一二三四五六七八九十百千零\d]+章',
            r'^Chapter\s+\d+',
            r'^\d+[\.\、]',
            r'^第[一二三四五六七八九十百千零\d]+节',
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


def main():
    print("=" * 70)
    print("清理重复小说文件 — 保留章节最多的版本")
    print("=" * 70)

    # 1. 扫描所有txt文件
    all_files = []
    for root, dirs, files in os.walk(DOWNLOAD_DIR):
        for f in files:
            if f.endswith('.txt'):
                fp = Path(root) / f
                all_files.append(fp)

    print(f"\n扫描到 {len(all_files)} 个txt文件")

    # 2. 按规范化书名分组
    groups = defaultdict(list)
    for fp in all_files:
        stem = fp.stem
        # 去掉_dup_后缀
        if '_dup_' in stem:
            stem = stem.split('_dup_')[0]
        norm = normalize_title(stem)
        if norm:
            groups[norm].append(fp)

    # 3. 找出有重复的组
    duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"发现 {len(duplicate_groups)} 组重复书名")

    # 4. 逐组处理：保留章节最多的，删除其他
    total_deleted = 0
    total_saved_mb = 0
    group_count = 0

    for norm_title, files in duplicate_groups.items():
        group_count += 1
        # 对每个文件统计章节数和文件大小
        file_info = []
        for fp in files:
            size = fp.stat().st_size
            chapters = count_chapters_in_file(fp)
            file_info.append((fp, chapters, size))

        # 按章节数降序，章节数相同按大小降序
        file_info.sort(key=lambda x: (x[1], x[2]), reverse=True)

        keep = file_info[0]
        to_delete = file_info[1:]

        for fp, ch, size in to_delete:
            try:
                fp.unlink()
                total_deleted += 1
                total_saved_mb += size / 1024 / 1024
            except Exception as e:
                print(f"  删除失败: {fp.name} - {e}")

        if group_count % 50 == 0:
            print(f"  已处理 {group_count}/{len(duplicate_groups)} 组，删除 {total_deleted} 个文件，节省 {total_saved_mb:.1f} MB")

    print("\n" + "=" * 70)
    print("清理完成!")
    print(f"删除重复文件: {total_deleted} 个")
    print(f"节省空间: {total_saved_mb:.2f} MB")
    print("=" * 70)


if __name__ == '__main__':
    main()
