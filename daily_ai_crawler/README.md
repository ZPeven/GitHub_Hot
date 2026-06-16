# 🔥 AI 技术热点日报爬虫

每日自动抓取全球 AI 热点，生成结构化 Markdown 报告。覆盖大语言模型、AI Agent、强化学习、脉冲神经网络、世界模型等前沿领域，重点关注中国国内动态与**南京大学 LAMDA** 实验室成果。

> **推荐环境**: [VSCode](https://code.visualstudio.com/) + [Claude Code](https://claude.ai/code) 插件，AI 辅助调试和二次开发。

---

## 特性

| 能力 | 说明 |
|------|------|
| 🕷️ **8路并行抓取** | RSS / arXiv / GitHub / Semantic Scholar / HuggingFace Daily Papers / Web / NJU / Discovery |
| 🌐 **中英双语** | DeepSeek API 自动翻译新闻标题，报告双语对照 |
| 🏫 **NJU 专项** | 268 人 LAMDA 成员名单 + 中英文姓名精准匹配 |
| 🔍 **智能去重** | URL 规范化 + 内容指纹 + 标题相似度三重去重 |
| ⭐ **相关性评分** | 7 维度评分过滤低质内容 |
| 📝 **Markdown 日报** | 表格 + 摘要 + GitHub 项目榜 + NJU 专区 |
| ⚡ **< 3 分钟** | 实测 ~30 秒完成全流程 |

---

## 快速开始

### 1. 环境准备

项目使用 [mamba](https://mamba.readthedocs.io/)（兼容 conda）管理 Python 环境。

```bash
# 克隆项目
git clone <your-repo-url>
cd daily_ai_crawler

# 创建虚拟环境（只需一次）
mamba env create -f environment.yml

# 激活环境
mamba activate ai_crawler
```

### 2. 配置（必须）

```bash
# 从模板创建本地配置
cp config.local.yaml.example config.local.yaml
```

编辑 `config.local.yaml`：

```yaml
# GitHub Token (可选但推荐，提升API速率 60→5000次/小时)
# 获取: https://github.com/settings/tokens → Generate new token (classic)
# 权限: 只勾选 public_repo 即可
github_token: "ghp_xxxxxxxxxxxx"

# DeepSeek API Key (可选，用于新闻标题中英双语翻译)
# 获取: https://platform.deepseek.com → API Keys
# 不配置则报告仅显示原标题
deepseek_api_key: "sk-xxxxxxxxxxxx"

# 代理配置（仅中国大陆用户需要）
# 国外用户保持 use_proxy: false 即可
proxy: "http://127.0.0.1:你的端口"   # 你的代理地址
use_proxy: true                    # 国外用户设为 false
```

> **国外用户**: 无需代理。`use_proxy: false` 即可正常运行，所有 API（arXiv、Semantic Scholar、HuggingFace）均可直连。

### 3. 运行

```bash
# 完整运行（推荐）
python main.py -v

# Windows
run.bat -v

# Linux / macOS
bash run.sh -v
```

```bash
# 仅查看数据库统计
python main.py --stats

# 不抓取，仅用已有数据重新生成报告
python main.py --report-only
```

---

## 命令行选项

```
python main.py [选项]

  -v, --verbose    详细输出，显示每阶段耗时和条目数
  --no-proxy       本次运行不使用代理（覆盖 config.local.yaml 设置）
  --report-only    不抓取，仅从已有数据重新生成 Markdown 报告
  --stats          显示数据库统计信息（历史记录数、源站成功率等）
```

---

## 项目结构

```
daily_ai_crawler/
├── main.py                        # 主入口，6阶段流水线
├── config.py                      # 全局配置（关键词/评分/阈值）
├── config.local.yaml              # 🔒 本地敏感配置（gitignore）
├── config.local.yaml.example      # 配置模板
├── sources.yaml                   # 18个预置信息源 + 搜索模板
├── database.py                    # SQLite 数据库
├── reporter.py                    # Markdown 报告生成器
├── lamda_members.json             # LAMDA 268人成员名单
│
├── crawlers/                      # 爬虫模块
│   ├── base.py                    # 异步HTTP基类（代理/重试/限速）
│   ├── rss_fetcher.py             # RSS/Atom 订阅源
│   ├── arxiv_fetcher.py           # arXiv API 论文
│   ├── github_fetcher.py          # GitHub Trending + Search API
│   ├── semantic_scholar_fetcher.py # Semantic Scholar 论文 + 机构过滤
│   ├── huggingface_fetcher.py     # HF Daily Papers 社区投票
│   ├── web_scraper.py             # 通用网页抓取
│   ├── nju_scraper.py             # 南大官网 + arXiv NJU 搜索
│   └── discovery.py               # Bing News 搜索发现
│
├── processors/                    # 处理模块
│   ├── nlp_utils.py               # jieba 分词/关键词/相似度
│   ├── dedup.py                   # 三重去重策略
│   ├── classifier.py              # 6 领域自动分类
│   ├── relevance.py               # 7 维度相关性评分
│   └── lamda_matcher.py           # LAMDA 中英文姓名精确匹配
│
├── tools/                         # 工具脚本
│   ├── build_lamda_list.py        # 一键更新 LAMDA 成员名单
│   └── test_lamda_matcher.py      # LAMDA 匹配器单元测试
│
└── reports/                       # 📊 每日报告输出
    └── YYYY-MM-DD_AI_Hotspot_Report.md
```

---

## 信息源一览

| 爬虫 | 信息源 | 类型 | 需要认证 |
|------|--------|------|----------|
| RSS | 机器之心、量子位、雷锋网、36氪、Papers With Code | `rss` | 无 |
| arXiv | cs.AI / cs.LG / cs.CL / cs.MA | `api` | 无 |
| GitHub | Trending + Search API | `web`+`api` | Token(可选) |
| Semantic Scholar | 论文搜索 + 机构过滤 | `api` | 无 |
| HF Daily Papers | 社区投票热门论文 | `api` | 无 |
| Web | 知乎、掘金 | `web` | 无 |
| NJU | 南大官网 + LAMDA 实验室 | `web`+`api` | 无 |
| Discovery | Bing News 搜索发现 | `rss` | 无 |

---

## 南京大学 LAMDA 专项

自动追踪 **南京大学 LAMDA 实验室**（负责人：周志华教授）的最新成果。

### 检测策略

```
策略 1 ─ 作者精确匹配  268 人 LAMDA 名单（中/英）  → 极高置信度
策略 2 ─ LAMDA 成员名 + NJU 标识                   → 高置信度
策略 3 ─ NJU / Nanjing University 文本              → 中置信度
                              (自动排除南邮/南理工等)
```

### 更新名单

LAMDA 网站更新后，一键同步：

```bash
python tools/build_lamda_list.py
```

---

## 自定义

### 添加信息源

编辑 `sources.yaml`：

```yaml
sources:
  - name: "你的源名称"
    url: "https://example.com/rss"
    type: rss           # rss | web | api
    category: news      # news | academic | code | community
    priority: 8         # 1-10，越大越优先
    enabled: true
    tags: [ai, china]
```

### 添加 AI 关键词

编辑 `config.py` 中的 `DOMAIN_KEYWORDS`：

```python
"llm": {
    "weight": 3.0,
    "zh": ["大语言模型", "LLM", ...],  # 中文关键词
    "en": ["large language model", ...],  # 英文关键词
},
```

### 调整报告条目上限

```python
# config.py
MAX_REPORT_ITEMS = 50   # 报告最多收录条目
MIN_RELEVANCE_SCORE = 2.0  # 最低相关性阈值
```

---

## 数据库

使用 SQLite 存储，文件 `crawler.db`（已 gitignore）：

| 表 | 说明 |
|----|------|
| `history` | 历史抓取记录（URL、标题、评分、分类） |
| `source_stats` | 源站抓取统计（成功率、平均响应时间） |
| `discovered_sites` | 发现的新网站 |
| `reports_meta` | 每日报告元数据 |

```bash
# 查看统计
python main.py --stats
```

---

## 定时运行（可选）

### Linux / macOS cron

```bash
# 每天早上 9 点运行
crontab -e
# 添加：
7 9 * * * cd /path/to/daily_ai_crawler && mamba run -n ai_crawler python main.py
```

### Windows 任务计划程序

```
任务计划程序 → 创建基本任务 → 每天 9:00
操作: 启动程序
程序: mamba
参数: run -n ai_crawler python main.py
起始于: D:\Git_Repositorys\GitHub_Hot\daily_ai_crawler
```

---

## VSCode + Claude Code 推荐

本项目推荐在 **VSCode** 中使用 **Claude Code** 插件进行二次开发：

1. 安装 [Claude Code](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code) VSCode 插件
2. 在项目目录下打开 Claude Code 面板
3. 直接用自然语言调试和扩展：
   - "帮我添加一个新的RSS源"
   - "调整LLM领域的关键词权重"
   - "为什么Semantic Scholar返回少了，帮我Debug"

`.vscode/` 目录已 gitignore，你可以自行配置 workspace settings。

---

## 常见问题

<details>
<summary><b>报错: ModuleNotFoundError: No module named 'xxx'</b></summary>

未激活虚拟环境。先运行 `mamba activate ai_crawler` 或使用 `mamba run -n ai_crawler python main.py`。
</details>

<details>
<summary><b>GitHub API 返回 403？</b></summary>

未配置 Token 时 API 限制为 60次/小时。编辑 `config.local.yaml` 添加 `github_token`。
</details>

<details>
<summary><b>如何启用中英双语翻译？</b></summary>

在 [DeepSeek 开放平台](https://platform.deepseek.com) 申请 API Key，编辑 `config.local.yaml`：
```yaml
deepseek_api_key: "sk-xxxxxxxxxxxx"
```
仅翻译新闻标题（论文标题和项目名保持原文）。DeepSeek 为国内服务，通常不需要代理。
</details>

<details>
<summary><b>中国大陆用户无法访问 arXiv / GitHub？</b></summary>

在 `config.local.yaml` 中配置代理：
```yaml
proxy: "http://127.0.0.1:你的端口"
use_proxy: true
```
</details>

<details>
<summary><b>国外用户需要做什么特殊配置？</b></summary>

无需任何特殊配置。保持 `use_proxy: false`，所有服务均可直连。
</details>

<details>
<summary><b>Semantic Scholar 返回数据很少？</b></summary>

免费版限制 100 次请求/5 分钟。如果批量添加了过多搜索查询，会被暂时限流。等待几分钟后重试。
</details>

<details>
<summary><b>Bing News 搜索返回空？</b></summary>

Bing News RSS 根据 IP 地理位置返回结果。如果你的代理出口在日本/美国，中文搜索可能返回空。此情况不影响抓取（还有其他 7 个爬虫）。
</details>

<details>
<summary><b>如何贡献新的信息源？</b></summary>

欢迎 PR！在 `sources.yaml` 中添加源配置，或在 `crawlers/` 中新增爬虫模块。
</details>

---

## License

MIT
