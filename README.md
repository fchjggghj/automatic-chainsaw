# automatic-chainsaw

智能小说爬虫下载器：面向快穿、无限流、综影视、综漫等题材的小说搜索、过滤、下载与去重工具。

项目采用 **Flask Web 后端 + 原生 HTML/JavaScript 前端 + 异步爬虫引擎**。启动后可以在浏览器里配置关键词、选择站点、查看搜索结果、手动或自动下载，并通过历史记录和日志跟踪任务进度。

> 本项目仅用于学习、研究和处理你有权访问的文本资源。请遵守目标网站规则、版权要求和当地法律，不要高频请求或批量下载未授权内容。

## 功能特性

- 多关键词搜索：支持快穿、无限流、综影视、综漫、系统文、穿书等关键词组合。
- 多站点处理器：内置笔趣阁系、TXT 下载站、帝国 CMS 系、通用搜索等站点处理器。
- 正则过滤：从标题、简介和正文样本中识别目标题材，减少无关结果。
- 自动/手动下载：支持“搜索后自动下载”和“仅搜索后勾选下载”两种流程。
- 去重与版本替换：按规范化书名比对，章节更多的新版本可替换旧版本。
- 实时进度：Web 页面轮询展示搜索、过滤、下载、失败、跳过等状态。
- 下载历史：使用 SQLite 记录下载历史、任务状态和统计信息。
- 本地 Web UI：无需前端构建工具，直接运行 Flask 服务即可使用。

## 仓库结构

```text
.
├── books/
│   ├── classify_kuaichuan.py          # 已下载文本的快穿分类辅助脚本
│   └── novel_crawler/                 # 主爬虫目录，包含额外整理脚本
│       ├── main.py                    # Flask Web 服务入口
│       ├── config.json                # 关键词、站点、下载目录、服务端口等配置
│       ├── requirements.txt           # Python 依赖
│       ├── crawler/                   # 爬虫核心模块
│       ├── web/                       # 前端页面
│       └── 项目说明书.md              # 更完整的内部说明
├── novel_crawler_2/                   # 并行配置副本，默认端口 8766
├── novel_crawler_3/                   # 并行配置副本，默认端口 8767
├── novel_crawler_4/                   # 并行配置副本，默认端口 8768
├── novel_crawler_5/                   # 并行配置副本，默认端口 8769
├── .gitignore                         # 排除下载数据、数据库、日志和缓存
└── README.md
```

`novel_crawler_2` 到 `novel_crawler_5` 的核心代码基本一致，主要用于使用不同端口并行运行多个实例。首次使用可以从 `novel_crawler_5` 开始。

## 快速开始

### 1. 进入项目目录

```powershell
git clone https://github.com/fchjggghj/automatic-chainsaw.git
cd automatic-chainsaw\novel_crawler_5
```

如果已经在本地有仓库，直接进入实际仓库目录下的 `novel_crawler_5` 即可。

### 2. 创建虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

主要依赖：

- `flask`
- `flask-cors`
- `aiohttp`
- `beautifulsoup4`
- `aiofiles`
- `lxml`

### 4. 检查配置

打开 `config.json`，重点确认：

- `server.port`：Web 服务端口，`novel_crawler_5` 默认是 `8769`。
- `download.output_dir`：下载输出目录。当前配置可能是本机绝对路径，换机器或换目录后建议改成你自己的路径。
- `crawler.request_delay`：请求间隔，默认较保守，避免过快访问目标站点。
- `search.keywords`：默认搜索关键词列表。

### 5. 启动 Web 服务

```powershell
python main.py
```

启动后浏览器会自动打开：

```text
http://127.0.0.1:8769
```

如果浏览器没有自动打开，可以手动访问上面的地址。

## 使用流程

1. 在页面中确认或添加关键词。
2. 选择要搜索的站点，默认可使用全部站点。
3. 点击“开始搜索”执行搜索并自动下载，或点击“仅搜索”先查看结果。
4. 在结果列表中按来源、状态筛选。
5. 勾选需要的小说并点击“下载选中”，也可以单本下载。
6. 在“运行日志”“下载历史”“统计信息”中查看任务状态。

## 常用脚本

在任意 `novel_crawler_*` 目录中可使用：

```powershell
python main.py             # 启动 Web UI
python run_all.py          # 按配置批量运行
python run_by_keyword.py   # 按关键词运行
python check_progress.py   # 检查进度
python test_serial.py      # 串行流程测试
```

`books/novel_crawler` 目录中还包含额外整理脚本：

```powershell
python cleanup_duplicates.py
python fix_downloaded_texts.py
python multi_fission.py
python organize_by_type_and_catalog.py
```

## 配置说明

`config.json` 的核心结构如下：

```json
{
  "search": {
    "keywords": ["快穿", "无限流", "综影视"],
    "max_pages": 999,
    "results_per_site": 999999
  },
  "crawler": {
    "concurrency": 1,
    "request_delay": 3.0,
    "timeout": 60,
    "retry_count": 3
  },
  "download": {
    "output_dir": "downloads",
    "max_file_size_mb": 50,
    "verify_content": true,
    "auto_unzip": true
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8769,
    "auto_open": true
  }
}
```

建议根据自己的环境调整：

- 将 `download.output_dir` 改为本机有效目录。
- 端口冲突时修改 `server.port`。
- 请求失败较多时增大 `crawler.request_delay` 或减少搜索范围。
- 只想测试流程时，先降低 `search.max_pages`。

## API 概览

启动服务后可使用这些本地接口：

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/` | GET | Web 首页 |
| `/api/config` | GET/POST | 读取或保存配置 |
| `/api/run` | POST | 启动搜索并自动下载 |
| `/api/search` | POST | 仅搜索，不自动下载 |
| `/api/stop` | POST | 停止当前任务 |
| `/api/progress` | GET | 获取实时进度 |
| `/api/results` | GET | 获取搜索结果，支持分页和过滤 |
| `/api/download` | POST | 批量下载选中结果 |
| `/api/download-single` | POST | 单本下载 |
| `/api/history` | GET | 下载历史 |
| `/api/stats` | GET | 统计信息 |
| `/api/logs` | GET | 运行日志 |
| `/api/sites` | GET | 已注册站点列表 |

## 数据与 Git

仓库不会提交这些本地运行产物：

- `downloads/`
- `history.db`
- `crawler.log`
- `monitor.log`
- `__pycache__/`
- `.venv/`
- SQLite 数据库和临时日志

也就是说，GitHub 上保存的是代码、配置和说明文档；实际下载文本、历史数据库和运行日志会留在本地。

## 常见问题

### 启动后打不开页面

确认端口没有被占用，并查看终端输出的实际地址。如果端口冲突，修改 `config.json` 中的 `server.port`。

### 下载目录不存在或写入失败

修改 `download.output_dir` 为当前机器上的有效路径，或手动创建该目录。

### 搜索结果很少

可以检查关键词、站点可用性和网络环境。部分站点临时不可访问是正常情况。

### 请求失败较多

适当增大 `crawler.request_delay`，减少一次性搜索站点数量，并避免过高频访问。

## 许可证

当前仓库暂未声明开源许可证。如需公开分发或协作开发，建议补充合适的 LICENSE 文件。
