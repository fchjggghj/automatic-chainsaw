from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import zipfile
from pathlib import Path


TEXT_SUFFIXES = {".txt", ".text", ".md"}


def decode_text(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "gb18030", "gbk", "big5"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("gb18030", errors="replace"), "gb18030-replace"


def is_zip(data: bytes) -> bool:
    return data.startswith(b"PK\x03\x04")


def is_html_text(text: str) -> bool:
    prefix = text[:1000].lower()
    return "<html" in prefix or "<!doctype html" in prefix or "<head" in prefix


def pick_zip_entry(zf: zipfile.ZipFile) -> zipfile.ZipInfo | None:
    entries = [entry for entry in zf.infolist() if not entry.is_dir()]
    text_entries = [
        entry
        for entry in entries
        if Path(entry.filename).suffix.lower() in TEXT_SUFFIXES
    ]
    candidates = text_entries or entries
    if not candidates:
        return None
    return max(candidates, key=lambda entry: entry.file_size)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + "\n"


def extract_download_links(text: str) -> str:
    links = re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.I)
    interesting = [
        html.unescape(link)
        for link in links
        if "DownSoft" in link or "download" in link.lower() or "down" in link.lower()
    ]
    return " | ".join(dict.fromkeys(interesting))


def convert_one(src: Path, out_dir: Path, resume: bool = False) -> dict[str, str]:
    row = {
        "source": str(src),
        "output": "",
        "kind": "",
        "encoding": "",
        "status": "",
        "note": "",
    }

    expected_target = out_dir / src.name
    if resume and expected_target.exists():
        row.update(output=str(expected_target), kind="existing", status="already_exists")
        return row

    data = src.read_bytes()
    if not data:
        row.update(kind="empty", status="skipped", note="empty file")
        return row

    text: str
    if is_zip(data):
        row["kind"] = "zip"
        try:
            with zipfile.ZipFile(src) as zf:
                entry = pick_zip_entry(zf)
                if entry is None:
                    row.update(status="failed", note="zip has no files")
                    return row
                inner_data = zf.read(entry)
            text, encoding = decode_text(inner_data)
            row["encoding"] = encoding
            row["note"] = entry.filename
        except Exception as exc:
            row.update(status="failed", note=f"zip error: {exc}")
            return row
    else:
        text, encoding = decode_text(data)
        row["encoding"] = encoding
        row["kind"] = "html" if is_html_text(text) else "text"
        if row["kind"] == "html":
            links = extract_download_links(text)
            row.update(status="skipped", note=f"html download page; links={links[:500]}")
            return row

    if is_html_text(text):
        links = extract_download_links(text)
        row.update(kind="html", status="skipped", note=f"html download page; links={links[:500]}")
        return row

    target = unique_path(out_dir / src.name)
    target.write_text(clean_text(text), encoding="utf-8-sig", newline="\n")
    row.update(output=str(target), status="converted")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert downloaded novel files to readable UTF-8 Chinese text.")
    parser.add_argument("input_dir", type=Path, help="Directory containing downloaded .txt files")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for converted text files")
    parser.add_argument("--limit", type=int, default=0, help="Convert only the first N files")
    parser.add_argument("--resume", action="store_true", help="Skip files whose converted output already exists")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    out_dir = (args.output_dir or (input_dir / "正常中文")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(
        path
        for path in input_dir.glob("*.txt")
        if path.is_file() and out_dir not in path.parents
    )
    if args.limit:
        files = files[: args.limit]

    report_path = out_dir / "_conversion_report.csv"
    counts: dict[str, int] = {}

    with report_path.open("w", encoding="utf-8-sig", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=["source", "output", "kind", "encoding", "status", "note"])
        writer.writeheader()

        for index, src in enumerate(files, 1):
            row = convert_one(src, out_dir, resume=args.resume)
            writer.writerow(row)
            key = f"{row['status']}:{row['kind']}"
            counts[key] = counts.get(key, 0) + 1

            if index % 100 == 0 or index == len(files):
                print(f"{index}/{len(files)} {src.name} -> {row['status']} ({row['kind']})", flush=True)

    print("DONE")
    print(f"Input: {input_dir}")
    print(f"Output: {out_dir}")
    print(f"Report: {report_path}")
    for key in sorted(counts):
        print(f"{key} = {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
