# ============================================================
# API 接口需求清单 — 用于增强 AI 热点爬虫
# ============================================================

apis:
  # ── 1. GitHub REST API (增强现有) ──────────────────
  - name: "GitHub REST API"
    endpoint: "https://api.github.com"
    auth: "Personal Access Token (classic)"  # 可选但强烈推荐
    auth_url: "https://github.com/settings/tokens"
    scope: "public_repo (只读即可)"
    rate_limit:
      anonymous: "60次/小时"
      authenticated: "5000次/小时"
    usage:
      - "/search/repositories?q=AI+agent&sort=stars&per_page=10"
      - "/repos/{owner}/{repo}"                          # 仓库详情
      - "/repos/{owner}/{repo}/topics"                   # 主题标签
      - "/repos/{owner}/{repo}/releases/latest"          # 最新发布
      - "/search/repositories?q=user:NJU+org:NJU"        # NJU组织仓库
    benefit: >
      替代HTML Trending页面解析(选择器脆弱的)，用API获取精确的
      stars/forks/topics/description数据。
      Token只需public_repo权限，安全无风险。
    priority: 高
    free: true (无需token也可用，但有token速率更高)

  # ── 2. Semantic Scholar API (新增!) ──────────────────
  - name: "Semantic Scholar Academic Graph API"
    endpoint: "https://api.semanticscholar.org/graph/v1"
    auth: "无需认证 (免费)"
    rate_limit: "100次/5分钟 (无key)"
    usage:
      - "/paper/search?query=large+language+model&limit=20&fieldsOfStudy=Computer Science"
      - "/paper/search?query=Nanjing+University&limit=20"  # 南大论文
      - "/paper/batch?fields=title,authors,abstract,citationCount,influentialCitationCount"
      - "/author/search?query=Zhi-Hua+Zhou"                 # 周志华等南大教授
    benefit: >
      替代部分arXiv XML解析。Semantic Scholar有更好的
      元数据（引用计数、影响力评分、作者机构归一化），
      尤其适合"南京大学"作者过滤——可以直接搜affiliation！
      arXiv API完全没有按机构过滤的能力。
    priority: 高
    free: true

  # ── 3. Hugging Face Daily Papers API (新增!) ──────────
  - name: "Hugging Face Daily Papers"
    endpoint: "https://huggingface.co/api/daily_papers"
    auth: "无需认证"
    rate_limit: "宽松"
    usage:
      - "GET /api/daily_papers"                              # 当日热门论文
      - "GET /api/daily_papers?date=2026-06-14"              # 指定日期
    benefit: >
      HuggingFace社区每日投票的热门ML论文，
      直接反映业界关注热点，质量很高。
      比arXiv原始列表更有"热点"价值。
    priority: 中
    free: true

  # ── 4. Papers With Code API (增强现有) ────────────────
  - name: "Papers With Code API"
    endpoint: "https://paperswithcode.com/api/v1"
    auth: "无需认证"
    rate_limit: "宽松 (建议加delay)"
    usage:
      - "/papers/?format=json"                               # 最新论文(含代码)
      - "/areas/ai/"                                         # AI领域概览
      - "/evaluation-tasks/"                                 # 评测任务排行榜
    benefit: >
      目前用的RSS，改为API可以获得结构化数据：
      代码链接、SOTA排名、任务分类。
    priority: 中
    free: true

  # ── 5. GitHub Personal Access Token (配置项) ──────────
  - name: "GitHub PAT (配置，非新API)"
    note: >
      在 config.py 中添加 GITHUB_TOKEN 配置项。
      只需在 GitHub Settings > Developer settings 创建
      classic token，勾选 public_repo (只读)。
      将匿名60次/小时的限制提升到5000次/小时。
      这是纯配置改动，不需要新代码。
    how_to_get: https://github.com/settings/tokens
    priority: 高
    cost: 免费

# ============================================================
# 不需要 API 的 (保持现有方案)
# ============================================================
no_api_needed:
  - "GitHub Trending 页面"       # GitHub官方没有Trending API，只能HTML
  - "知乎/掘金/36氪 等网页"       # 这些平台没有公开API
  - "RSS订阅 (机器之心/量子位等)"  # RSS是最佳方式，无需API
  - "Bing News 搜索"             # 没有免费API，RSS格式已够用
