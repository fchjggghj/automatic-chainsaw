from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path


QUICK_TERMS = ("快穿", "位面", "宿主", "任务者", "攻略系统", "炮灰系统", "反派系统")


CATEGORY_ORDER = [
    "01_无限流_副本逃生",
    "02_综影视",
    "03_综漫_动漫同人",
    "04_快穿_纯爱耽美",
    "05_快穿_百合GL",
    "06_快穿_穿书",
    "07_快穿_反派攻略拯救",
    "08_快穿_女配炮灰逆袭",
    "09_快穿_系统任务位面",
    "10_快穿_综合",
    "11_末世灵异悬疑",
    "12_其他",
]


def norm_text(value: str) -> str:
    return value.lower().replace(" ", "")


def has_any(text: str, terms: tuple[str, ...]) -> list[str]:
    folded = norm_text(text)
    return [term for term in terms if norm_text(term) in folded]


def classify(title: str, intro: str) -> tuple[str, str]:
    hay = f"{title}\n{intro}"
    quick = bool(has_any(hay, QUICK_TERMS))

    title_hits = has_any(title, ("无限流", "综影视", "综影", "综漫", "动漫"))
    if "无限流" in title_hits:
        return "01_无限流_副本逃生", "书名关键词：无限流"
    if "综影视" in title_hits or "综影" in title_hits:
        return "02_综影视", "书名关键词：综影视"
    if "综漫" in title_hits or "动漫" in title_hits:
        return "03_综漫_动漫同人", "书名关键词：综漫/动漫"

    rules: list[tuple[str, tuple[str, ...], bool]] = [
        ("01_无限流_副本逃生", ("无限流", "副本", "逃生", "通关", "规则怪谈", "惊悚游戏", "恐怖游戏", "无限游戏", "npc训练营", "npc", "boss战"), False),
        ("02_综影视", ("综影视", "综影", "影视", "甄嬛", "如懿", "还珠", "红楼", "知否", "香蜜", "莲花楼", "陈情令", "少年歌行", "三生三世", "霍格沃兹", "hp"), False),
        ("03_综漫_动漫同人", ("综漫", "动漫", "柯南", "名柯", "火影", "海贼", "鬼灭", "咒回", "网王", "家教", "死神", "银魂", "文野", "猎人", "圣斗士", "龙珠", "刀剑神域", "原神", "崩坏", "狐妖", "叶罗丽", "奥特", "假面骑士"), False),
        ("04_快穿_纯爱耽美", ("耽美", "纯爱", "bl", "主攻", "主受", "老攻", "渣攻", "总攻", "攻受", "男男", "受转攻", "男主攻", "男配攻"), True),
        ("05_快穿_百合GL", ("百合", "gl", "女同", "姬", "女主她总在弯", "弯gl", "影后", "女配gl"), True),
        ("06_快穿_穿书", ("穿书", "书穿", "穿进书", "书中游", "小说里", "文里", "穿成"), True),
        ("07_快穿_反派攻略拯救", ("反派", "boss", "男配", "攻略", "拯救", "救赎", "洗白", "黑化", "白月光", "金手指"), True),
        ("08_快穿_女配炮灰逆袭", ("女配", "炮灰", "逆袭", "打脸", "虐渣", "白莲花", "恶毒", "原配", "配角"), True),
        ("09_快穿_系统任务位面", ("系统", "任务", "宿主", "位面", "世界", "快穿", "穿越世界", "积分", "主神"), True),
        ("11_末世灵异悬疑", ("末世", "灵异", "悬疑", "恐怖", "鬼", "怪谈", "诡异", "惊悚"), False),
    ]

    for category, terms, require_quick in rules:
        if require_quick and not quick and "快穿" not in norm_text(title):
            continue
        hits = has_any(hay, terms)
        if hits:
            return category, "关键词：" + "、".join(hits[:8])

    if quick:
        return "10_快穿_综合", "关键词：快穿/位面/宿主/任务"
    return "12_其他", "未命中主要题材关键词"


INVALID_CHARS = r'<>:"/\|?*'


def safe_name(value: str, max_len: int = 80) -> str:
    value = value.strip().replace("\ufeff", "")
    value = "".join("_" if unicodedata.category(ch).startswith("C") else ch for ch in value)
    for ch in INVALID_CHARS:
        value = value.replace(ch, "_")
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" .")
    if not value:
        value = "未命名"
    return value[:max_len].rstrip(" .")


def short_hash(value: str) -> str:
    return hashlib.md5(value.encode("utf-8", errors="ignore")).hexdigest()[:8]


@dataclass
class NovelRecord:
    source: Path
    category: str
    reason: str
    title: str
    author: str
    status: str
    intro: str
    chapters: list[str]
    novel_dir: Path | None = None
    link_mode: str = ""


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def extract_metadata(text: str, path: Path) -> tuple[str, str, str, str]:
    head = text[:30000]
    title = path.stem
    author = ""
    status = ""
    intro = ""

    m = re.search(r"^『(?P<title>.*?)(?:/作者:(?P<author>.*?))?』", head, flags=re.M)
    if m:
        title = (m.group("title") or title).strip()
        author = (m.group("author") or "").strip()

    m = re.search(r"^『状态:(?P<status>.*?)』", head, flags=re.M)
    if m:
        status = m.group("status").strip()

    m = re.search(r"『内容简介:\s*(?P<intro>.*?)』", head, flags=re.S)
    if m:
        intro = re.sub(r"\s+", " ", m.group("intro")).strip()

    return title, author, status, intro


CHAPTER_START_RE = re.compile(
    r"^\s*(?:"
    r"第\s*[0-9０-９一二三四五六七八九十百千万两〇零]+\s*[章节回卷部集篇].{0,80}"
    r"|[0-9０-９一二三四五六七八九十百千万两〇零]+[、.．]\s*.{0,80}"
    r"|卷\s*[0-9０-９一二三四五六七八九十百千万两〇零]+.{0,80}"
    r"|正文(?:\s|$|[：:（(]).{0,40}"
    r"|序章.{0,40}|楔子.{0,40}|引言.{0,40}|前言.{0,40}|尾声.{0,40}"
    r"|番外.{0,60}|后记.{0,60}|完结感言.{0,60}"
    r"|[【\[].{1,60}[】\]]"
    r")\s*$"
)


def starts_indented(value: str) -> bool:
    return value.startswith((" ", "\t", "　"))


def has_sentence_end(value: str) -> bool:
    return bool(re.search(r"[。！？；，,、…]$", value.strip()))


def is_noise_title(value: str) -> bool:
    bad = ("爱下电子书", "章节内容开始", "内容简介", "txt版阅读", "https://", "http://", "e-mail", "下载和分享")
    folded = value.lower()
    return any(item in folded for item in bad)


def nonempty_around(lines: list[str], index: int, step: int) -> str:
    i = index + step
    while 0 <= i < len(lines):
        if lines[i].strip():
            return lines[i]
        i += step
    return ""


def looks_like_chapter_title(lines: list[str], index: int) -> bool:
    raw = lines[index]
    stripped = raw.strip()
    if not stripped or is_noise_title(stripped):
        return False
    if len(stripped) > 90:
        return False
    if CHAPTER_START_RE.match(stripped):
        return True

    if starts_indented(raw):
        return False
    if len(stripped) > 55 or has_sentence_end(stripped):
        return False
    if stripped in {"正文", "目录"}:
        return True

    prev_line = nonempty_around(lines, index, -1)
    next_line = nonempty_around(lines, index, 1)
    next_indented = bool(next_line and starts_indented(next_line))
    prev_indented = bool(prev_line and starts_indented(prev_line))
    has_number = bool(re.search(r"[0-9０-９一二三四五六七八九十百千万两〇零]+", stripped))
    has_arc_marker = any(ch in stripped for ch in ("篇", "卷", "世界", "副本", "番外", "结局", "修"))

    return next_indented and (prev_indented or has_number or has_arc_marker or index < 20)


def extract_chapters(text: str) -> list[str]:
    if "------章节内容开始-------" in text:
        body = text.split("------章节内容开始-------", 1)[1]
    else:
        body = text

    lines = body.splitlines()
    chapters: list[str] = []
    for i, _ in enumerate(lines):
        if looks_like_chapter_title(lines, i):
            title = re.sub(r"\s+", " ", lines[i].strip())
            if title and (not chapters or chapters[-1] != title):
                chapters.append(title)

    if not chapters:
        chapters = ["全文"]
    return chapters


def dir_matches_source(path: Path, source: Path) -> bool:
    info_path = path / "小说信息.txt"
    if not info_path.exists():
        return False
    try:
        return str(source) in info_path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return False


def make_unique_dir(parent: Path, base_name: str, source: Path) -> Path:
    base = safe_name(base_name, 72)
    candidate = parent / base
    if not candidate.exists() or dir_matches_source(candidate, source):
        return candidate

    hashed = parent / f"{base}_{short_hash(str(source))}"
    if not hashed.exists() or dir_matches_source(hashed, source):
        return hashed

    i = 1
    while True:
        numbered = parent / f"{base}_{short_hash(str(source))}_{i}"
        if not numbered.exists() or dir_matches_source(numbered, source):
            return numbered
        i += 1


def hardlink_or_copy(src: Path, dst: Path) -> str:
    if dst.exists():
        return "exists"
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def write_novel_files(record: NovelRecord, out_root: Path) -> None:
    category_dir = out_root / record.category
    category_dir.mkdir(parents=True, exist_ok=True)

    folder_label = f"{record.title}_{record.author}" if record.author else record.source.stem
    novel_dir = make_unique_dir(category_dir, folder_label, record.source)
    novel_dir.mkdir(parents=True, exist_ok=True)
    record.novel_dir = novel_dir

    source_target = novel_dir / "原文.txt"
    record.link_mode = hardlink_or_copy(record.source, source_target)

    info_lines = [
        f"书名：{record.title}",
        f"作者：{record.author or '未知'}",
        f"状态：{record.status or '未知'}",
        f"分类：{record.category}",
        f"分类依据：{record.reason}",
        f"章节数：{len(record.chapters)}",
        f"原始文件：{record.source}",
        f"正文文件：{source_target.name}",
        "",
        "简介：",
        record.intro or "无",
        "",
    ]
    (novel_dir / "小说信息.txt").write_text("\n".join(info_lines), encoding="utf-8-sig")

    catalog_lines = [
        f"《{record.title}》章节目录",
        f"作者：{record.author or '未知'}",
        f"分类：{record.category}",
        f"章节数：{len(record.chapters)}",
        "",
    ]
    catalog_lines.extend(f"{i:04d}. {chapter}" for i, chapter in enumerate(record.chapters, 1))
    (novel_dir / "目录.txt").write_text("\n".join(catalog_lines) + "\n", encoding="utf-8-sig")


def write_category_catalogs(records: list[NovelRecord], out_root: Path) -> None:
    by_category: dict[str, list[NovelRecord]] = {}
    for record in records:
        by_category.setdefault(record.category, []).append(record)

    for category in CATEGORY_ORDER:
        category_records = by_category.get(category, [])
        if not category_records:
            continue
        category_dir = out_root / category
        total_chapters = sum(len(record.chapters) for record in category_records)
        lines = [
            f"分类：{category}",
            f"小说数：{len(category_records)}",
            f"章节名总数：{total_chapters}",
            "",
        ]
        for record in sorted(category_records, key=lambda item: item.title):
            rel = record.novel_dir.relative_to(category_dir) if record.novel_dir else Path("")
            lines.append(f"【{record.title}】 作者：{record.author or '未知'} 章节数：{len(record.chapters)} 目录：{rel}")
            lines.extend(f"  {i:04d}. {chapter}" for i, chapter in enumerate(record.chapters, 1))
            lines.append("")
        (category_dir / "分类目录.txt").write_text("\n".join(lines), encoding="utf-8-sig")

        csv_path = category_dir / "章节目录.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["分类", "小说", "作者", "章节序号", "章节名", "小说目录"])
            for record in sorted(category_records, key=lambda item: item.title):
                rel = str(record.novel_dir.relative_to(category_dir)) if record.novel_dir else ""
                for i, chapter in enumerate(record.chapters, 1):
                    writer.writerow([category, record.title, record.author, i, chapter, rel])


def write_global_reports(records: list[NovelRecord], out_root: Path) -> None:
    stats: dict[str, tuple[int, int]] = {}
    for record in records:
        count, chapters = stats.get(record.category, (0, 0))
        stats[record.category] = (count + 1, chapters + len(record.chapters))

    with (out_root / "_总分类索引.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["分类", "书名", "作者", "状态", "章节数", "分类依据", "小说目录", "原文件", "链接模式"])
        for record in sorted(records, key=lambda item: (item.category, item.title)):
            writer.writerow([
                record.category,
                record.title,
                record.author,
                record.status,
                len(record.chapters),
                record.reason,
                str(record.novel_dir or ""),
                str(record.source),
                record.link_mode,
            ])

    lines = ["分类统计", ""]
    for category in CATEGORY_ORDER:
        if category in stats:
            count, chapters = stats[category]
            lines.append(f"{category}: 小说 {count} 本，章节名 {chapters} 个")
    lines.append("")
    lines.append(f"总小说数：{len(records)}")
    lines.append(f"总章节名数：{sum(len(record.chapters) for record in records)}")
    (out_root / "_分类统计.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def build_records(input_dir: Path, limit: int = 0) -> list[NovelRecord]:
    files = sorted(input_dir.glob("*.txt"))
    if limit:
        files = files[:limit]

    records: list[NovelRecord] = []
    for index, path in enumerate(files, 1):
        text = read_text(path)
        title, author, status, intro = extract_metadata(text, path)
        chapters = extract_chapters(text)
        category, reason = classify(title, intro)
        records.append(NovelRecord(path, category, reason, title, author, status, intro, chapters))
        if index % 200 == 0 or index == len(files):
            print(f"scanned {index}/{len(files)}: {path.name} -> {category} ({len(chapters)} chapters)", flush=True)
    return records


def print_summary(records: list[NovelRecord]) -> None:
    stats: dict[str, tuple[int, int]] = {}
    for record in records:
        count, chapters = stats.get(record.category, (0, 0))
        stats[record.category] = (count + 1, chapters + len(record.chapters))
    for category in CATEGORY_ORDER:
        if category in stats:
            count, chapters = stats[category]
            print(f"{category}: novels={count}, chapter_titles={chapters}")
    print(f"TOTAL: novels={len(records)}, chapter_titles={sum(len(record.chapters) for record in records)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify novels and build per-category/per-novel chapter catalogs.")
    parser.add_argument("input_dir", type=Path, help="Directory containing readable UTF-8 novel .txt files")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output root. Default: sibling 分类整理")
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N files")
    parser.add_argument("--dry-run", action="store_true", help="Scan and print category counts without writing output")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    out_root = (args.output_dir or (input_dir.parent / "分类整理")).resolve()

    records = build_records(input_dir, args.limit)
    print_summary(records)

    if args.dry_run:
        return 0

    out_root.mkdir(parents=True, exist_ok=True)
    for index, record in enumerate(records, 1):
        write_novel_files(record, out_root)
        if index % 200 == 0 or index == len(records):
            print(f"organized {index}/{len(records)}: {record.title} -> {record.category}", flush=True)

    write_category_catalogs(records, out_root)
    write_global_reports(records, out_root)
    print(f"DONE: {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
