"""
智能小说爬虫下载器 — 主入口
启动 Flask Web 服务 + 串行爬虫引擎
"""
import sys
import json
import threading
import asyncio
import logging
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from crawler.engine import CrawlerEngine, TaskStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_DIR / "crawler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("main")

app = Flask(__name__, static_folder=str(PROJECT_DIR / "web"), static_url_path="")
CORS(app)

engine = CrawlerEngine(
    config_path=PROJECT_DIR / "config.json",
    on_log=lambda msg: log.info(msg),
)

log_queue: list[dict] = []


def add_log(msg: str):
    global log_queue
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "msg": msg}
    log_queue.append(entry)
    if len(log_queue) > 500:
        log_queue = log_queue[-500:]
    log.info(msg)


# ---- 后台运行引擎 ----

_engine_loop: asyncio.AbstractEventLoop = None
_engine_thread: threading.Thread = None


def _run_engine(keywords: list[str], site_names: list[str] = None, auto_download: bool = True):
    """在后台线程中运行引擎（串行模式）"""
    global _engine_loop
    _engine_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_engine_loop)
    try:
        stats = _engine_loop.run_until_complete(
            engine.run(keywords=keywords, auto_download=auto_download, site_names=site_names)
        )
        add_log(f"[完成] 搜索{stats['searched']} | 过滤{stats['filtered']} | "
                f"下载{stats['downloaded']} | 失败{stats['failed']} | 跳过{stats['skipped']}")
    except Exception as e:
        add_log(f"[引擎异常] {e}")
    finally:
        _engine_loop.close()
        _engine_loop = None


# ---- API 路由 ----

@app.route("/")
def index():
    web_dir = PROJECT_DIR / "web"
    if (web_dir / "index.html").exists():
        return send_from_directory(str(web_dir), "index.html")
    return jsonify({"status": "running", "message": "小说爬虫API服务已启动，无前端页面"})


@app.route("/progress")
def progress_page():
    web_dir = PROJECT_DIR / "web"
    if (web_dir / "progress.html").exists():
        return send_from_directory(str(web_dir), "progress.html")
    return jsonify({"status": "running"})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        cfg_path = PROJECT_DIR / "config.json"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                return jsonify(json.load(f))
        return jsonify({})
    else:
        data = request.get_json()
        cfg_path = PROJECT_DIR / "config.json"
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})


@app.route("/api/run", methods=["POST"])
def api_run():
    """启动完整串行流程：搜索 → 过滤 → 下载"""
    if engine._running:
        return jsonify({"ok": False, "message": "引擎正在运行中"}), 409

    data = request.get_json() or {}
    keywords = data.get("keywords", engine._search_keywords)
    site_names = data.get("site_names", None)  # 指定站点
    auto_download = data.get("auto_download", True)

    global _engine_thread
    _engine_thread = threading.Thread(
        target=_run_engine,
        args=(keywords, site_names, auto_download),
        daemon=True,
    )
    _engine_thread.start()

    add_log(f"[API] 启动串行爬虫: 关键词={keywords}, 站点={site_names or '全部'}")
    return jsonify({"ok": True, "message": "串行爬虫已启动"})


@app.route("/api/search", methods=["POST"])
def api_search():
    """仅搜索，不下载"""
    if engine._running:
        return jsonify({"ok": False, "message": "引擎正在运行中"}), 409

    data = request.get_json() or {}
    keywords = data.get("keywords", engine._search_keywords)
    site_names = data.get("site_names", None)

    def run():
        global _engine_loop
        _engine_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_engine_loop)
        try:
            _engine_loop.run_until_complete(
                engine.run(keywords=keywords, auto_download=False, site_names=site_names)
            )
        finally:
            _engine_loop.close()
            _engine_loop = None

    global _engine_thread
    _engine_thread = threading.Thread(target=run, daemon=True)
    _engine_thread.start()

    add_log(f"[API] 搜索: 关键词={keywords}, 站点={site_names or '全部'}")
    return jsonify({"ok": True, "message": "搜索已启动"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """停止当前任务"""
    engine.cancel()
    add_log("[API] 已发送停止信号")
    return jsonify({"ok": True, "message": "已发送停止信号，等待当前下载完成"})


@app.route("/api/progress", methods=["GET"])
def api_progress():
    """获取实时进度"""
    return jsonify(engine.get_progress())


@app.route("/api/results", methods=["GET"])
def api_results():
    """获取任务结果列表（支持分页和过滤）"""
    status_filter = request.args.get("status", None)
    source_filter = request.args.get("source", None)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    results = engine.get_results()
    if status_filter:
        results = [r for r in results if r["status"] == status_filter]
    if source_filter:
        results = [r for r in results if r["source"] == source_filter]

    total = len(results)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_results = results[start:end]

    # 获取所有来源（用于过滤）
    all_sources = sorted(set(r["source"] for r in engine.get_results() if r.get("source")))

    return jsonify({
        "results": page_results,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "sources": all_sources,
        "progress": engine.get_progress(),
    })


@app.route("/api/download", methods=["POST"])
def api_download():
    """批量下载选中的小说"""
    if engine._running:
        return jsonify({"ok": False, "message": "引擎正在运行中"}), 409

    data = request.get_json() or {}
    results = data.get("results", [])

    if not results:
        return jsonify({"ok": False, "message": "未选择任何小说"}), 400

    # 将选中结果的信息注入引擎的任务列表，然后启动下载
    def run():
        global _engine_loop
        _engine_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_engine_loop)
        try:
            _engine_loop.run_until_complete(
                engine.download_selected(results)
            )
        except Exception as e:
            add_log(f"[下载异常] {e}")
        finally:
            _engine_loop.close()
            _engine_loop = None

    global _engine_thread
    _engine_thread = threading.Thread(target=run, daemon=True)
    _engine_thread.start()

    add_log(f"[API] 批量下载: {len(results)} 本小说")
    return jsonify({"ok": True, "message": f"开始下载 {len(results)} 本小说"})


@app.route("/api/download-single", methods=["POST"])
def api_download_single():
    """下载单本小说"""
    if engine._running:
        return jsonify({"ok": False, "message": "引擎正在运行中"}), 409

    data = request.get_json() or {}
    title = data.get("title", "")
    url = data.get("url", "")
    source = data.get("source", "")

    if not url:
        return jsonify({"ok": False, "message": "缺少小说URL"}), 400

    def run():
        global _engine_loop
        _engine_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_engine_loop)
        try:
            _engine_loop.run_until_complete(
                engine.download_single(title=title, url=url, source=source)
            )
        except Exception as e:
            add_log(f"[下载异常] {e}")
        finally:
            _engine_loop.close()
            _engine_loop = None

    global _engine_thread
    _engine_thread = threading.Thread(target=run, daemon=True)
    _engine_thread.start()

    add_log(f"[API] 单本下载: {title}")
    return jsonify({"ok": True, "message": f"开始下载: {title}"})


@app.route("/api/download-url", methods=["POST"])
def api_download_url():
    """获取单个小说的下载链接"""
    data = request.get_json() or {}
    url = data.get("url", "")

    async def get_url():
        return await engine.get_download_url(url)

    loop = asyncio.new_event_loop()
    dl_url = loop.run_until_complete(get_url())
    loop.close()

    return jsonify({"download_url": dl_url or ""})


@app.route("/api/history", methods=["GET"])
def api_history():
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    records = engine.history.get_history(limit, offset)
    return jsonify([{
        "id": r.id, "title": r.title, "author": r.author,
        "url": r.url, "category": r.category, "filepath": r.filepath,
        "file_size": r.file_size, "status": r.status,
        "site_name": r.site_name, "match_method": r.match_method,
        "match_detail": r.match_detail, "created_at": r.created_at,
        "completed_at": r.completed_at,
    } for r in records])


@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify(engine.history.get_stats())


@app.route("/api/logs", methods=["GET"])
def api_logs():
    limit = request.args.get("limit", 100, type=int)
    return jsonify({"logs": log_queue[-limit:]})


@app.route("/api/dedup/stats", methods=["GET"])
def api_dedup_stats():
    return jsonify(engine.dedup.get_stats())


@app.route("/api/sites", methods=["GET"])
def api_sites():
    """获取所有已注册的站点列表"""
    sites = []
    if engine._handlers:
        for h in engine._handlers:
            sites.append({
                "name": h.config.name,
                "base_url": h.config.base_url,
                "handler": type(h).__name__,
            })
    else:
        # 引擎未初始化时，从配置文件读取站点列表
        cfg = engine.config
        for site_cfg in cfg.get("sites", []):
            if site_cfg.get("enabled", True):
                sites.append({
                    "name": site_cfg.get("name", ""),
                    "base_url": site_cfg.get("base_url", ""),
                    "handler": site_cfg.get("handler", ""),
                })
    return jsonify({"sites": sites})


def main():
    cfg = {}
    cfg_path = PROJECT_DIR / "config.json"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)

    server_cfg = cfg.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = server_cfg.get("port", 8765)
    auto_open = server_cfg.get("auto_open", True)

    add_log(f"启动服务器: http://{host}:{port}")

    if auto_open:
        import webbrowser
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
