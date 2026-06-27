#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快穿小说自动分类脚本 v2.0
=====================
扫描指定目录下所有小说文件夹，通过多种方法识别"快穿"类小说，
并将识别结果归类到目标目录。

识别策略（按优先级，任一命中即判定为快穿）:
  1. 目录名强关键词匹配（快穿/无限流等）
  2. 简介文件标签行 【快穿+…】 模式
  3. 简介文件内容强关键词 + 多世界叙事模式（"世界一："）
  4. 主文件名强关键词匹配
  5. 正文内容高可信模式扫描（首8000字节）

注意：书库中每本书目录下可能有「剧情世界」子目录存放分章节文件，
      这是通用存储结构，不作为快穿判据。
"""

import re
import shutil
import logging
import argparse
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# 配置区（可直接修改或通过命令行参数覆盖）
# ─────────────────────────────────────────────

ROOT_DIR     = r"C:\Users\Administrator\Desktop\books"
TARGET_DIR   = r"C:\Users\Administrator\Desktop\books\06-穿越脑洞\快穿"
LOG_FILE     = r"C:\Users\Administrator\Desktop\books\classify_kuaichuan_log.txt"
DRY_RUN      = False          # True=仅预览 False=实际移动
CONTENT_SCAN_BYTES = 8000     # 正文扫描字节数

# 已是快穿目录，跳过扫描
SKIP_RELATIVE_PATHS = {
    "06-穿越脑洞/快穿",
}

# ─────────────────────────────────────────────
# 关键词 / 模式定义
# ─────────────────────────────────────────────

# 目录名 / 主文件名强命中词（出现即认定为快穿，无需其他信号）
STRONG_TITLE_KW = [
    "快穿", "快穿系统", "快穿之", "快穿攻略", "快穿文",
    "无限流", "无限副本", "无限游戏", "无限恐怖", "无限世界",
    "穿书攻略", "炮灰攻略系统",
]

# 简介标签行（如「标签：快穿 系统」）强命中词
SYNOPSIS_TAG_STRONG_KW = [
    "快穿", "无限流", "无限副本",
]

# 简介正文中的强信号词（需要在简介中出现，而非普通章节文）
SYNOPSIS_CONTENT_KW = [
    "快穿", "无限流", "无限副本", "穿越多个世界",
    "炮灰攻略系统", "穿书攻略系统",
]

# 简介正文中的多世界叙事模式（如"世界一：""第一个世界"）
SYNOPSIS_WORLD_PATTERNS = [
    r"世界[一二三四五六七八九十\d][：:：\s]",   # 世界一：
    r"第[一二三四五六七八九十百零\d]+个世界",      # 第一个世界
    r"(世界|副本)(一|二|三|四|五|六|七|八|九|十|\d+)[：:\s]",
    r"\[快穿",                                    # 简介开头常见格式
    r"【快穿",
    r"（快穿",
]

# 正文内容高可信模式（首段）——单独命中即判定为快穿
# 核心：必须是「多世界切换」信号，单世界穿书文不含这些
CONTENT_HIGH_CONFIDENCE_PATTERNS = [
    r"第[一二三四五六七八九十百零\d]+个世界",
    r"(世界|副本)(完成|结束|通关|任务完成)",
    r"(下一个|下个|下一)(世界|副本)",
    r"世界[一二三四五六七八九十\d][：:：]",     # 世界一：/世界1：
    r"进入(了|下)?第[一二三四五六七八九十百零\d]+(个)?(世界|副本)",
]

# 正文内容弱信号（需与辅助词配合才判定）
CONTENT_WEAK_PATTERNS = [
    r"恭喜宿主",
    r"任务(完成|失败)",
    r"宿主[，,。！!]",
]

# 弱信号配套辅助词（必须在正文里同时出现）
# 只选快穿场景特有的词，穿书/系统单世界文一般不含
CONTENT_WEAK_BOOSTER_KW = [
    "快穿", "无限流",
    "副本完成", "下一个世界", "穿越世界",
    "炮灰攻略系统", "系统任务列表",
    "世界积分", "积分兑换",
]

# 简介文件名模式
SYNOPSIS_FILE_RE = re.compile(r"^00_.*简介.*\.txt$", re.IGNORECASE)

# ─────────────────────────────────────────────
# 日志初始化
# ─────────────────────────────────────────────

def setup_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("kc_classify")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="w")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


log: logging.Logger = None  # 在 main() 中初始化

# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def _read_text(path: Path, max_bytes: int = CONTENT_SCAN_BYTES) -> str:
    """尝试多种编码读取文件前 max_bytes 字节，失败返回空串。"""
    for enc in ("utf-8", "gbk", "utf-8-sig", "gb18030"):
        try:
            with open(path, "rb") as f:
                raw = f.read(max_bytes)
            return raw.decode(enc, errors="ignore")
        except Exception:
            continue
    return ""


def _contains_any(text: str, keywords: list[str]) -> tuple[bool, str]:
    """检查 text 是否包含任意关键词，返回 (是否命中, 命中词)。"""
    tl = text.lower()
    for kw in keywords:
        if kw.lower() in tl:
            return True, kw
    return False, ""


def _pattern_match(text: str, patterns: list[str]) -> tuple[bool, str]:
    """正则匹配，返回 (是否命中, 命中片段)。"""
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return True, m.group(0)
    return False, ""


def _find_synopsis(book_dir: Path) -> Path | None:
    """在书目录或其子目录中查找简介文件（00_*简介*.txt）。"""
    for f in book_dir.rglob("*.txt"):
        if SYNOPSIS_FILE_RE.match(f.name):
            return f
    return None


def _find_main_txt(book_dir: Path) -> Path | None:
    """找到最大的非简介 txt 作为主文件。"""
    candidates = [
        f for f in book_dir.rglob("*.txt")
        if f.is_file() and not SYNOPSIS_FILE_RE.match(f.name)
    ]
    return max(candidates, key=lambda p: p.stat().st_size) if candidates else None

# ─────────────────────────────────────────────
# 核心识别逻辑
# ─────────────────────────────────────────────

def classify_book(book_dir: Path) -> tuple[bool, str, str]:
    """
    判断一本书是否为快穿。
    返回: (is_kuaichuan: bool, method: str, evidence: str)
    """
    dir_name = book_dir.name

    # ── 方法1：目录名强关键词 ──────────────────────────
    hit, kw = _contains_any(dir_name, STRONG_TITLE_KW)
    if hit:
        return True, "目录名关键词", kw

    # ── 方法2 & 3：简介文件分析 ───────────────────────
    synopsis = _find_synopsis(book_dir)
    if synopsis:
        text = _read_text(synopsis, max_bytes=3000)
        if text:
            # 2a. 标签行中的强关键词
            tag_m = re.search(r"标签[：:](.*)", text)
            if tag_m:
                tag_line = tag_m.group(1)
                hit, kw = _contains_any(tag_line, SYNOPSIS_TAG_STRONG_KW)
                if hit:
                    return True, "简介标签", kw

            # 2b. 简介正文强关键词
            hit, kw = _contains_any(text, SYNOPSIS_CONTENT_KW)
            if hit:
                return True, "简介内容关键词", kw

            # 2c. 简介中的多世界叙事模式（【快穿+…】、世界一：等）
            hit, ev = _pattern_match(text, SYNOPSIS_WORLD_PATTERNS)
            if hit:
                return True, "简介多世界叙事", ev

    # ── 方法4：主文件名强关键词 ─────────────────────────
    main_txt = _find_main_txt(book_dir)
    if main_txt:
        hit, kw = _contains_any(main_txt.name, STRONG_TITLE_KW)
        if hit:
            return True, "主文件名关键词", kw

        # ── 方法5：正文内容扫描 ──────────────────────────
        content = _read_text(main_txt, max_bytes=CONTENT_SCAN_BYTES)
        if content:
            # 5a. 高可信模式：单独命中即判定
            hit, ev = _pattern_match(content, CONTENT_HIGH_CONFIDENCE_PATTERNS)
            if hit:
                return True, "正文内容扫描(强)", ev
            # 5b. 弱信号 + 辅助词双重命中才判定
            weak_hit, weak_ev = _pattern_match(content, CONTENT_WEAK_PATTERNS)
            if weak_hit:
                boost_hit, boost_kw = _contains_any(content, CONTENT_WEAK_BOOSTER_KW)
                if boost_hit:
                    return True, "正文内容扫描(弱+辅)", f"{weak_ev} + {boost_kw}"

    return False, "", ""

# ─────────────────────────────────────────────
# 目录扫描
# ─────────────────────────────────────────────

def _is_skip(path: Path, root: Path) -> bool:
    """判断路径是否在跳过列表中。"""
    try:
        rel = str(path.relative_to(root)).replace("\\", "/")
        return any(rel.startswith(s) for s in SKIP_RELATIVE_PATHS)
    except ValueError:
        return False


def find_book_dirs(root: Path) -> list[Path]:
    """
    收集所有「书」级目录。
    策略：找出所有直接含 .txt 文件的目录，
    然后去掉那些其祖先目录也含 .txt 的（保留最顶层）。
    """
    all_txt_dirs: set[Path] = set()

    for d in root.rglob("*"):
        if not d.is_dir():
            continue
        if _is_skip(d, root):
            continue
        try:
            if any(f.is_file() and f.suffix == ".txt" for f in d.iterdir()):
                all_txt_dirs.add(d)
        except PermissionError:
            continue

    # 保留「最顶层」含 txt 的目录（祖先中无其他含 txt 目录）
    book_dirs = []
    for d in all_txt_dirs:
        parent = d.parent
        depth = 0
        is_child = False
        while parent != root and depth < 6:
            if parent in all_txt_dirs:
                is_child = True
                break
            parent = parent.parent
            depth += 1
        if not is_child:
            book_dirs.append(d)

    return sorted(book_dirs)

# ─────────────────────────────────────────────
# 移动操作
# ─────────────────────────────────────────────

def move_book(book_dir: Path, target_dir: Path) -> Path:
    """移动书目录到目标目录，自动处理同名冲突。"""
    dest = target_dir / book_dir.name
    if dest.exists():
        i = 1
        while dest.exists():
            dest = target_dir / f"{book_dir.name}_{i}"
            i += 1
    shutil.move(str(book_dir), str(dest))
    return dest

# ─────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────

def main():
    global CONTENT_SCAN_BYTES, log

    parser = argparse.ArgumentParser(
        description="快穿小说自动分类脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root",        default=ROOT_DIR,   help="根书库目录")
    parser.add_argument("--target",      default=TARGET_DIR, help="快穿目标目录")
    parser.add_argument("--log",         default=LOG_FILE,   help="日志文件路径")
    parser.add_argument("--dry-run",     action="store_true", default=DRY_RUN,
                        help="仅预览，不实际移动（推荐先运行一次确认）")
    parser.add_argument("--scan-bytes",  type=int, default=CONTENT_SCAN_BYTES,
                        help=f"正文扫描字节数（默认{CONTENT_SCAN_BYTES}）")
    args = parser.parse_args()

    CONTENT_SCAN_BYTES = args.scan_bytes
    log = setup_logger(args.log)

    root    = Path(args.root)
    target  = Path(args.target)
    dry_run = args.dry_run

    if not root.exists():
        log.error(f"根目录不存在: {root}")
        return

    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)

    mode = "【预览模式 · 不移动文件】" if dry_run else "【执行模式 · 将移动文件】"
    log.info("=" * 60)
    log.info(f"快穿小说自动分类脚本 v2.0  {mode}")
    log.info(f"根目录  : {root}")
    log.info(f"目标目录: {target}")
    log.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    log.info("正在扫描书库目录（可能需要几秒）…")
    book_dirs = find_book_dirs(root)
    total = len(book_dirs)
    log.info(f"共发现 {total} 个书目录")
    log.info("")

    matched:   list[tuple[Path, str, str]] = []
    unmatched: list[Path] = []
    errors:    list[tuple[Path, str]] = []

    for i, book_dir in enumerate(book_dirs, 1):
        try:
            is_kc, method, evidence = classify_book(book_dir)
            rel = book_dir.relative_to(root)
            if is_kc:
                matched.append((book_dir, method, evidence))
                log.info(f"[{i:05d}/{total}] ✓ 快穿 │ {rel}")
                log.info(f"              识别方式: {method}  依据: {evidence}")
            else:
                unmatched.append(book_dir)
                log.debug(f"[{i:05d}/{total}] - 未匹配 │ {rel}")
        except Exception as e:
            errors.append((book_dir, str(e)))
            log.warning(f"[{i:05d}/{total}] ! 异常  │ {book_dir.name} │ {e}")

    # ── 汇总 ─────────────────────────────────────────
    log.info("")
    log.info("=" * 60)
    log.info(f"扫描完成 | 共 {total} 本")
    log.info(f"  ✓ 识别为快穿 : {len(matched)} 本")
    log.info(f"  - 未匹配     : {len(unmatched)} 本")
    log.info(f"  ! 处理异常   : {len(errors)} 本")
    log.info("=" * 60)

    if not matched:
        log.info("没有识别到快穿小说。")
        return

    # ── 移动 ─────────────────────────────────────────
    log.info("")
    if dry_run:
        log.info("【预览】以下书目录将被移动到目标目录：")
        for book_dir, method, evidence in matched:
            rel = book_dir.relative_to(root)
            log.info(f"  {rel}  →  {target / book_dir.name}")
        log.info("")
        log.info(f"预览完成：共 {len(matched)} 本将被移动。")
        log.info("确认无误后，去掉 --dry-run 参数重新运行即可正式归类。")
    else:
        log.info("开始移动文件…")
        moved, failed = 0, 0
        for book_dir, method, evidence in matched:
            rel = book_dir.relative_to(root)
            try:
                dest = move_book(book_dir, target)
                log.info(f"  [移动] {rel}  →  {dest.relative_to(root)}")
                moved += 1
            except Exception as e:
                log.error(f"  [失败] {rel}  │  {e}")
                failed += 1
        log.info("")
        log.info(f"移动完成：成功 {moved} 本，失败 {failed} 本")

    log.info(f"日志已保存至: {args.log}")
    log.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
