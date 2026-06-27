"""
爬虫自动化监控脚本
功能：
1. 检查Flask服务器是否存活，不存活则重启
2. 检查爬虫引擎是否在运行，空闲则自动启动搜索+下载
3. 记录监控日志
"""
import subprocess
import sys
import time
import json
import urllib.request
import os
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
LOG_FILE = PROJECT_DIR / "monitor.log"
PID_FILE = PROJECT_DIR / "server.pid"

ALL_KEYWORDS = [
    "快穿", "无限流", "综影视", "综漫", "诸天流", "副本攻略", "炮灰逆袭", "炮灰攻略",
    "穿书攻略", "系统文", "穿越万界", "位面穿越", "多世界", "无限副本", "世界任务",
    "积分兑换", "世界穿梭", "万界穿行", "穿书", "快穿甜宠", "快穿逆袭", "快穿HE",
    "#快穿#", "#无限流#", "#综影视#", "#综漫#", "#副本#", "#炮灰攻略#", "#系统文#",
    "#穿书#", "#快穿 HE#", "#快穿 甜宠#", "#快穿 逆袭#", "#无限副本#", "#诸天流#",
]

SERVER_URL = "http://127.0.0.1:8765"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def server_is_alive():
    """检查Flask服务器是否存活"""
    try:
        resp = urllib.request.urlopen(f"{SERVER_URL}/api/progress", timeout=5)
        return resp.status == 200
    except Exception:
        return False


def get_progress():
    """获取爬虫进度"""
    try:
        resp = urllib.request.urlopen(f"{SERVER_URL}/api/progress", timeout=5)
        return json.loads(resp.read())
    except Exception:
        return None


def start_server():
    """启动Flask服务器"""
    log("正在启动Flask服务器...")
    try:
        # 先杀掉旧进程
        if PID_FILE.exists():
            old_pid = PID_FILE.read_text().strip()
            try:
                os.system(f"taskkill /PID {old_pid} /F >nul 2>&1")
            except Exception:
                pass
            PID_FILE.unlink(missing_ok=True)

        # 启动新进程
        proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=str(PROJECT_DIR),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        PID_FILE.write_text(str(proc.pid))
        log(f"Flask服务器已启动, PID={proc.pid}")

        # 等待服务器就绪
        for i in range(30):
            time.sleep(1)
            if server_is_alive():
                log("Flask服务器已就绪")
                return True
        log("Flask服务器启动超时")
        return False
    except Exception as e:
        log(f"启动服务器失败: {e}")
        return False


def start_crawler():
    """启动爬虫任务"""
    try:
        data = json.dumps({
            "keywords": ALL_KEYWORDS,
            "auto_download": True,
            "site_names": None,
        }).encode()
        req = urllib.request.Request(
            f"{SERVER_URL}/api/run",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if result.get("ok"):
            log(f"爬虫已启动: {len(ALL_KEYWORDS)}个关键词")
            return True
        else:
            log(f"爬虫启动失败: {result.get('message')}")
            return False
    except Exception as e:
        log(f"启动爬虫异常: {e}")
        return False


def monitor():
    """执行一次监控检查"""
    log("=" * 50)
    log("监控检查开始")

    # 1. 检查服务器
    if not server_is_alive():
        log("服务器未运行，尝试启动...")
        if not start_server():
            log("服务器启动失败，下次再试")
            return
        time.sleep(2)

    # 2. 获取进度
    prog = get_progress()
    if not prog:
        log("无法获取进度，服务器可能异常")
        return

    stats = prog.get("stats", {})
    tasks = prog.get("tasks", {})
    running = prog.get("running", False)

    log(f"状态: {'运行中' if running else '空闲'}")
    log(f"当前: 关键词={prog.get('current_keyword','-')} 站点={prog.get('current_site','-')} 小说={prog.get('current_novel','-')}")
    log(f"统计: 搜索={stats.get('searched',0)} 过滤={stats.get('filtered',0)} 下载={stats.get('downloaded',0)} 失败={stats.get('failed',0)} 跳过={stats.get('skipped',0)} 替换={stats.get('replaced',0)}")
    log(f"任务: 总计={tasks.get('total',0)} 完成={tasks.get('completed',0)} 失败={tasks.get('failed',0)} 跳过={tasks.get('skipped',0)}")

    # 3. 如果爬虫空闲，自动启动
    if not running:
        log("爬虫空闲，自动启动搜索+下载...")
        start_crawler()

    log("监控检查完成")


if __name__ == "__main__":
    monitor()
