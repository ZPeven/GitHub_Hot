"""
Markdown 每日报告生成器
"""

import os
import datetime
from config import REPORTS_DIR, DOMAIN_KEYWORDS


class Reporter:
    """生成格式化的 Markdown 每日AI热点报告"""

    DOMAIN_NAMES = {
        "llm": "🤖 大语言模型 (LLM)",
        "lwm": "🌍 世界模型 (LWM)",
        "snn": "🧠 脉冲神经网络 (SNN)",
        "rl": "🎮 强化学习 (RL)",
        "ml": "📊 机器学习 (ML)",
        "agent": "🕹️ AI Agent",
        "nju": "🏫 南京大学AI成果",
    }

    EMOJI_MAP = {
        "llm": "🤖", "lwm": "🌍", "snn": "🧠", "rl": "🎮",
        "ml": "📊", "agent": "🕹️", "code": "💻", "academic": "📄",
        "nju": "🏫", "news": "📰", "community": "💬",
    }

    def generate(self, items: list[dict], stats: dict) -> str:
        """生成完整 Markdown 报告"""
        today = datetime.date.today()
        now = datetime.datetime.now()

        lines = []
        lines.append(f"# 🔥 AI技术热点日报")
        lines.append(f"")
        lines.append(f"**日期**: {today.isoformat()} ({today.strftime('%A')})")
        lines.append(f"**生成时间**: {now.strftime('%H:%M:%S')}")
        lines.append(f"**数据来源**: {stats.get('sources_used', 0)} 个信息源")
        lines.append(f"**收录条目**: {stats.get('total_items', 0)} 条")
        lines.append(f"**NJU成果**: {stats.get('nju_items', 0)} 条 | **GitHub项目**: {stats.get('github_items', 0)} 个")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

        # 目录
        lines.append(f"## 📑 目录")
        lines.append(f"")
        for domain, name in self.DOMAIN_NAMES.items():
            count = stats.get("domain_counts", {}).get(domain, 0)
            if count > 0:
                lines.append(f"- [{name}](#{domain}) ({count}条)")
        lines.append(f"")
        lines.append(f"---")

        # 按领域分组
        grouped = self._group_by_domain(items)

        for domain in ["llm", "lwm", "snn", "rl", "ml", "agent"]:
            domain_items = grouped.get(domain, [])
            if not domain_items:
                continue

            name = self.DOMAIN_NAMES.get(domain, domain)
            lines.append(f"")
            lines.append(f'<a id="{domain}"></a>')
            lines.append(f"## {name}")
            lines.append(f"")
            lines.append(f"| # | 标题 | 来源 | 评分 |")
            lines.append(f"|---|------|------|------|")

            for i, item in enumerate(domain_items, 1):
                title = item.get("title", "Untitled")
                title_zh = item.get("title_zh", "")
                url = item.get("url", "#")
                source = item.get("source_name", "Unknown")[:15]
                score = item.get("relevance_score", 0)
                nju_flag = " 🏫" if item.get("is_nju") else ""

                # 双语显示：非中文标题附加中文翻译
                if title_zh and title_zh != title:
                    display = f"{title[:60]}<br>🇨🇳 {title_zh[:60]}"
                else:
                    display = title[:80]
                lines.append(f"| {i} | {display}{nju_flag} | {source} | {score:.1f} |")

            # 热门话题摘要
            lines.append(f"")
            lines.append(f"### 📝 {name} 热点摘要")
            lines.append(f"")
            top_items = domain_items[:5]
            for i, item in enumerate(top_items, 1):
                title = item.get("title", "Untitled")
                title_zh = item.get("title_zh", "")
                url = item.get("url", "#")
                summary = item.get("summary", "")
                summary_zh = item.get("summary_zh", "")
                if summary:
                    if title_zh and title_zh != title:
                        lines.append(f"**{i}. [{title}]({url})**")
                        lines.append(f"   🇨🇳 {title_zh}")
                    else:
                        lines.append(f"**{i}. [{title}]({url})**")
                    if summary_zh and summary_zh != summary:
                        lines.append(f"> 🇨🇳 {summary_zh[:200]}")
                    lines.append(f"> {summary[:200]}")
                    lines.append(f"")

        # NJU专区
        nju_items = grouped.get("nju", [])
        if nju_items:
            lines.append(f"")
            lines.append(f'<a id="nju"></a>')
            lines.append(f"## 🏫 南京大学AI成果专区")
            lines.append(f"")
            lines.append(f"> 以下是最新收录的南京大学相关AI研究成果")
            lines.append(f"")
            for i, item in enumerate(nju_items, 1):
                title = item.get("title", "")
                title_zh = item.get("title_zh", "")
                url = item.get("url", "#")
                summary = item.get("summary", "")
                summary_zh = item.get("summary_zh", "")
                authors = item.get("authors", [])
                display_title = f"{title} / {title_zh}" if title_zh else title
                lines.append(f"### {i}. [{display_title}]({url})")
                if authors:
                    lines.append(f"**作者**: {', '.join(authors[:8])}")
                if summary:
                    if summary_zh and summary_zh != summary:
                        lines.append(f"> 🇨🇳 {summary_zh[:250]}")
                    lines.append(f"> {summary[:250]}")
                lines.append(f"")

        # GitHub热门项目
        github_items = [it for it in items if it.get("is_github")]
        if github_items:
            lines.append(f"")
            lines.append(f"## 💻 GitHub AI 热点项目")
            lines.append(f"")
            lines.append(f"| # | 项目 | 语言 | ⭐ Stars | 简介 |")
            lines.append(f"|---|------|------|---------|------|")

            for i, item in enumerate(github_items[:15], 1):
                title = item.get("title", "").replace(" ", " ")
                url = item.get("url", "#")
                lang = item.get("language", "")
                stars = item.get("stars", "")
                summary = item.get("summary", "").split(" — ")[-1] if " — " in item.get("summary", "") else ""

                lines.append(f"| {i} | [{title}]({url}) | {lang} | {stars} | {summary[:60]} |")

        # 数据统计
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## 📊 数据统计")
        lines.append(f"")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 总抓取条目 | {stats.get('total_fetched', 0)} |")
        lines.append(f"| 去重后条目 | {stats.get('after_dedup', 0)} |")
        lines.append(f"| 相关性过滤后 | {stats.get('total_items', 0)} |")
        lines.append(f"| GitHub项目 | {stats.get('github_items', 0)} |")
        lines.append(f"| NJU成果 | {stats.get('nju_items', 0)} |")
        lines.append(f"| 新发现网站 | {stats.get('discovered_sites', 0)} |")
        lines.append(f"| 使用源数量 | {stats.get('sources_used', 0)} |")
        lines.append(f"| 处理耗时 | {stats.get('elapsed_seconds', 0):.1f}s |")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"*本报告由 AI Hotspot Crawler 自动生成 | {today.isoformat()}*")

        return "\n".join(lines)

    def _group_by_domain(self, items: list[dict]) -> dict[str, list]:
        """按子领域分组"""
        groups = {}
        for item in items:
            # NJU特殊处理
            if item.get("is_nju"):
                groups.setdefault("nju", []).append(item)

            domain = item.get("sub_category", "ml")
            groups.setdefault(domain, []).append(item)
        return groups

    def save(self, content: str, date_str: str = None) -> str:
        """保存报告到文件"""
        if date_str is None:
            date_str = datetime.date.today().isoformat()
        filename = f"{date_str}_AI_Hotspot_Report.md"
        filepath = os.path.join(REPORTS_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath
