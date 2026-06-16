"""
每日AI热点爬虫 — 全局配置
敏感信息 (Token/代理) 请放在 config.local.yaml (已gitignore)
"""

import os
import yaml

# ============================================================
# 加载本地配置 (config.local.yaml，gitignore不提交)
# ============================================================
_LOCAL_CONFIG = {}
_local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.local.yaml")
if os.path.exists(_local_path):
    with open(_local_path, "r", encoding="utf-8") as f:
        _LOCAL_CONFIG = yaml.safe_load(f) or {}

# ============================================================
# 项目路径
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
SOURCES_FILE = os.path.join(BASE_DIR, "sources.yaml")
DB_FILE = os.path.join(BASE_DIR, "crawler.db")

# ============================================================
# API 密钥配置 (敏感信息 → config.local.yaml)
# ============================================================
GITHUB_TOKEN = _LOCAL_CONFIG.get("github_token", "")
DEEPSEEK_API_KEY = _LOCAL_CONFIG.get("deepseek_api_key", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1"
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"

# 翻译并发数 (≤200)
TRANSLATION_CONCURRENCY = 30

# ============================================================
# 代理配置 (敏感信息 → config.local.yaml)
# ============================================================
PROXY_URL = _LOCAL_CONFIG.get("proxy", "")
USE_PROXY = _LOCAL_CONFIG.get("use_proxy", False)

PROXIES = {
    "http": PROXY_URL,
    "https": PROXY_URL,
} if USE_PROXY and PROXY_URL else None

# ============================================================
# 请求配置
# ============================================================
REQUEST_TIMEOUT = 15          # 单次请求超时(秒)
MAX_RETRIES = 2               # 最大重试次数
RETRY_DELAY = 1.0             # 重试间隔(秒)
POLITE_DELAY = 1.0            # 同域名请求间隔(秒)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 "
    "AICrawler/1.0 (Research Bot; ai-hotspot-tracker)"
)
PARALLEL_LIMIT = 8            # 并发请求上限

# ============================================================
# 处理时限 (秒) — 硬性上限
# ============================================================
MAX_RUNTIME_SECONDS = 175     # 留buffer给报告+翻译+清理

# ============================================================
# 每个来源最大抓取条目数
# ============================================================
MAX_ITEMS_PER_RSS = 12
MAX_ITEMS_PER_GITHUB = 15
MAX_ITEMS_PER_ARXIV = 10
MAX_ITEMS_PER_SEARCH = 8
MAX_ITEMS_PER_DISCOVERY = 5
MAX_ITEMS_SEMANTIC_SCHOLAR = 15
MAX_ITEMS_HF_PAPERS = 10

# ============================================================
# 相关性评分阈值
# ============================================================
MIN_RELEVANCE_SCORE = 2.0     # 低于此分不收录
MAX_REPORT_ITEMS = 50         # 报告最多条目数

# ============================================================
# AI 领域关键词 (权重越高越相关)
# ============================================================
DOMAIN_KEYWORDS = {
    # LLM / 大语言模型
    "llm": {
        "weight": 3.0,
        "zh": ["大语言模型", "大模型", "语言模型", "LLM", "GPT", "Claude", "Gemini",
               "文心一言", "通义千问", "混元", "盘古", "ChatGLM", "百川",
               "预训练", "微调", "SFT", "RLHF", "DPO", "对齐", "幻觉",
               "上下文窗口", "长文本", "RAG", "检索增强", "MoE", "混合专家"],
        "en": ["large language model", "LLM", "GPT", "transformer", "pretrain",
               "fine-tune", "SFT", "RLHF", "DPO", "RAG", "MoE", "mixture of experts",
               "context window", "hallucination", "alignment", "instruction tuning"],
    },
    # LWM / 世界模型
    "lwm": {
        "weight": 2.5,
        "zh": ["世界模型", "LWM", "World Model", "视频生成", "物理仿真",
               "Sora", "视频理解", "时空建模", "三维重建", "NeRF", "3D生成"],
        "en": ["world model", "LWM", "video generation", "physics simulation",
               "Sora", "video understanding", "spatiotemporal", "3D reconstruction",
               "NeRF", "gaussian splatting", "embodied"],
    },
    # 脉冲神经网络
    "snn": {
        "weight": 2.5,
        "zh": ["脉冲神经网络", "SNN", "类脑计算", "神经形态", "脉冲编码",
               "Spike", "LIF神经元", "事件驱动", "存内计算", "忆阻器"],
        "en": ["spiking neural network", "SNN", "neuromorphic", "spike-timing",
               "LIF neuron", "event-driven", "memristor", "brain-inspired"],
    },
    # 强化学习
    "rl": {
        "weight": 2.5,
        "zh": ["强化学习", "RL", "深度强化学习", "DQN", "PPO", "策略梯度",
               "Q学习", "Actor-Critic", "多智能体", "自博弈", "奖励建模",
               "RLHF", "GRPO", "决策大模型"],
        "en": ["reinforcement learning", "deep RL", "PPO", "DQN", "policy gradient",
               "actor-critic", "multi-agent RL", "self-play", "reward modeling",
               "RLHF", "GRPO", "decision transformer"],
    },
    # 机器学习
    "ml": {
        "weight": 2.0,
        "zh": ["机器学习", "深度学习", "神经网络", "Transformer", "扩散模型",
               "生成模型", "自监督学习", "对比学习", "联邦学习", "知识蒸馏",
               "剪枝", "量化", "模型压缩", "迁移学习", "元学习"],
        "en": ["machine learning", "deep learning", "neural network", "transformer",
               "diffusion model", "self-supervised", "contrastive learning",
               "federated learning", "knowledge distillation", "pruning",
               "quantization", "transfer learning", "meta-learning"],
    },
    # Agent 技术
    "agent": {
        "weight": 3.0,
        "zh": ["AI Agent", "智能体", "自主代理", "多Agent", "工具调用",
               "Function Call", "代码生成", "自动化", "Copilot", "Devin",
               "AutoGPT", "工作流", "编排", "记忆机制", "反思", "规划",
               "MCP协议", "工具使用", "人机协同"],
        "en": ["AI agent", "autonomous agent", "multi-agent", "tool use",
               "function calling", "code generation", "Copilot", "Devin",
               "AutoGPT", "workflow", "orchestration", "memory mechanism",
               "reflection", "planning", "human-AI collaboration", "MCP"],
    },
}

# ============================================================
# 南京大学专项关键词
# ============================================================
NJU_KEYWORDS = [
    "南京大学", "Nanjing University", "NJU", "南大",
    "Nanjing Univ", "NJU CS", "NJU AI", "LAMDA", "NLP Group NJU",
]

# ============================================================
# 来源权威度权重 (用于评分加成)
# ============================================================
SOURCE_AUTHORITY = {
    "arxiv": 0.9,
    "github_trending": 0.85,
    "jiqizhixin": 0.8,
    "qbitai": 0.8,
    "leiphone": 0.75,
    "36kr": 0.7,
    "zhihu": 0.5,
    "semantic scholar": 0.9,
    "hf daily": 0.85,
    "semantic_scholar": 0.9,
    "huggingface": 0.85,
    "paperswithcode": 0.85,
    "nju_official": 0.9,
    "search_discovery": 0.4,
    "unknown": 0.3,
}

# 确保输出目录存在
os.makedirs(REPORTS_DIR, exist_ok=True)
