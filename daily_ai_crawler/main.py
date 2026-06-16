#!/usr/bin/env python3
"""
🔥 AI技术热点日报爬虫 — 主入口
每日运行一次，3分钟内完成抓取、处理、报告生成

免责声明 / DISCLAIMER:
  本软件仅供个人学习研究使用。使用者应遵守各信息源的使用条款、
  robots.txt 协议及当地法律法规。所有抓取内容版权归原作者所有。
  本软件不用于任何商业目的。

  This software is for PERSONAL EDUCATIONAL USE ONLY.
"""

import os
import sys
import time
import asyncio
import datetime
import traceback
import argparse

import yaml
import aiohttp

from config import (
    SOURCES_FILE, MAX_RUNTIME_SECONDS, MAX_REPORT_ITEMS,
    USER_AGENT, PROXIES, DOMAIN_KEYWORDS,
)
from database import Database, make_fingerprint
from crawlers import (
    RSSFetcher, ArxivFetcher, GitHubFetcher,
    SemanticScholarFetcher, HuggingFaceFetcher,
    WebScraper, NJUScraper, DiscoveryCrawler,
)
from processors import (
    ChineseNLP, Deduplicator, Classifier, RelevanceScorer,
)
from processors.translator import Translator
from reporter import Reporter


class AIHotspotCrawler:
    """AI热点爬虫主控制器"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.db = Database()
        self.dedup = Deduplicator(self.db)
        self.classifier = Classifier()
        self.scorer = RelevanceScorer()
        self.reporter = Reporter()
        self.stats = {}
        self.start_time = None

    def log(self, msg: str):
        if self.verbose:
            print(f"  [{time.monotonic() - self.start_time:5.1f}s] {msg}")

    async def run(self) -> str:
        """执行完整的抓取→处理→报告流程"""
        self.start_time = time.monotonic()
        print(f"🚀 AI Hotspot Crawler 启动 — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   代理: {PROXIES['http'] if PROXIES else '无'}")

        # 加载信息源
        sources = self._load_sources()
        print(f"   已加载 {len(sources)} 个信息源")

        # 创建共享HTTP session
        connector = aiohttp.TCPConnector(limit=10, force_close=True)
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        ) as session:
            # 创建所有爬虫实例
            rss = RSSFetcher(session)
            arxiv_fetcher = ArxivFetcher(session)
            github = GitHubFetcher(session)
            semantic = SemanticScholarFetcher(session)
            hf_papers = HuggingFaceFetcher(session)
            web = WebScraper(session)
            nju = NJUScraper(session)
            discovery = DiscoveryCrawler(session)

            # ── 阶段1: 并行抓取所有源 ──────────────────
            print("\n📡 [阶段1] 并行抓取中...")
            phase1_start = time.monotonic()

            rss_sources = [s for s in sources if s.get("type") == "rss"]
            web_sources = [s for s in sources if s.get("type") == "web"]
            discovery_queries = sources if isinstance(sources, list) else []

            # 从yaml中提取discovery配置
            with open(SOURCES_FILE, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)
            discovery_queries = yaml_data.get("discovery_queries", [])

            results = []
            exceptions = []

            # 8路并行抓取
            tasks = [
                ("RSS订阅", rss.crawl(rss_sources)),
                ("arXiv论文", arxiv_fetcher.crawl()),
                ("GitHub热点", github.crawl()),
                ("Semantic Scholar", semantic.crawl()),
                ("HF Daily Papers", hf_papers.crawl()),
                ("Web抓取", web.crawl(web_sources)),
                ("南大专线", nju.crawl()),
                ("搜索发现", discovery.crawl(discovery_queries)),
            ]

            async def run_with_name(name, coro):
                try:
                    res = await asyncio.wait_for(coro, timeout=50)
                    return name, res, None
                except asyncio.TimeoutError:
                    return name, [], "超时"
                except Exception as e:
                    return name, [], str(e)

            task_results = await asyncio.gather(
                *[run_with_name(name, coro) for name, coro in tasks],
                return_exceptions=True,
            )

            for tr in task_results:
                if isinstance(tr, tuple):
                    name, res, err = tr
                    if err:
                        print(f"   ⚠️  {name}: 出错 ({err})")
                        exceptions.append((name, err))
                    else:
                        print(f"   ✅ {name}: 获取 {len(res)} 条")
                        results.extend(res)
                else:
                    exceptions.append(("unknown", str(tr)))

            phase1_elapsed = time.monotonic() - phase1_start
            total_fetched = len(results)
            print(f"   ⏱️  阶段1完成 ({phase1_elapsed:.1f}s), 共获取 {total_fetched} 条原始数据")

            # ── 阶段2: 去重 ──────────────────────────
            print("\n🔍 [阶段2] 智能去重中...")
            phase2_start = time.monotonic()
            deduped = self.dedup.deduplicate(results)
            after_dedup = len(deduped)
            removed = total_fetched - after_dedup
            print(f"   去除 {removed} 条重复, 剩余 {after_dedup} 条")
            print(f"   ⏱️  阶段2完成 ({time.monotonic() - phase2_start:.1f}s)")

            # ── 阶段3: 分类 ──────────────────────────
            print("\n🏷️  [阶段3] 领域分类中...")
            phase3_start = time.monotonic()
            classified = self.classifier.classify_all(deduped)
            print(f"   ⏱️  阶段3完成 ({time.monotonic() - phase3_start:.1f}s)")

            # ── 阶段4: 相关性评分与过滤 ──────────────
            print("\n⭐ [阶段4] 相关性评分中...")
            phase4_start = time.monotonic()
            filtered = self.scorer.filter(classified)
            after_filter = len(filtered)
            print(f"   过滤低相关条目: {after_dedup - after_filter} 条, 保留 {after_filter} 条")
            print(f"   ⏱️  阶段4完成 ({time.monotonic() - phase4_start:.1f}s)")

            # ── 阶段5: 截取TopN ──────────────────────
            final_items = filtered[:MAX_REPORT_ITEMS]

            # ── 阶段6: 中英翻译 (DeepSeek API) ────────
            print("\n🌐 [阶段6] 中英双语翻译中...")
            phase6_start = time.monotonic()
            translator = Translator()
            try:
                if translator.enabled:
                    final_items = await translator.translate_all(final_items)
                    translated_count = sum(1 for it in final_items if it.get("title_en"))
                    print(f"   已翻译 {translated_count} 条标题")
                else:
                    print("   ⚠️  未配置 DeepSeek API Key，跳过翻译")
            finally:
                await translator.close()
            print(f"   ⏱️  阶段6完成 ({time.monotonic() - phase6_start:.1f}s)")

            # ── 阶段7: 存入数据库 ────────────────────
            print("\n💾 [阶段7] 存入数据库...")
            phase5_start = time.monotonic()
            today = datetime.date.today().isoformat()
            saved = 0
            for item in final_items:
                item["report_date"] = today
                if "fingerprint" not in item:
                    item["fingerprint"] = make_fingerprint(
                        item.get("title", ""), item.get("summary", "")
                    )
                if self.db.insert_item(item):
                    saved += 1

            # 记录发现的陌生网站
            discovered_count = 0
            for item in final_items:
                if item.get("is_discovered") and item.get("domain"):
                    self.db.mark_discovered_site(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        domain=item.get("domain", ""),
                        category=item.get("sub_category", ""),
                    )
                    discovered_count += 1
            print(f"   已保存 {saved} 条, 发现 {discovered_count} 个新网站")
            print(f"   ⏱️  阶段7完成 ({time.monotonic() - phase5_start:.1f}s)")

        # ── 统计 ─────────────────────────────────────
        nju_count = sum(1 for it in final_items if it.get("is_nju"))
        github_count = sum(1 for it in final_items if it.get("is_github"))
        domain_counts = {}
        for it in final_items:
            d = it.get("sub_category", "ml")
            domain_counts[d] = domain_counts.get(d, 0) + 1

        # 使用的源数量
        used_sources = set(it.get("source_name", "") for it in final_items)

        total_elapsed = time.monotonic() - self.start_time

        self.stats = {
            "total_fetched": total_fetched,
            "after_dedup": after_dedup,
            "total_items": len(final_items),
            "sources_used": len(used_sources),
            "nju_items": nju_count,
            "github_items": github_count,
            "discovered_sites": discovered_count,
            "domain_counts": domain_counts,
            "elapsed_seconds": total_elapsed,
            "exceptions": len(exceptions),
        }

        # ── 阶段8: 生成报告 ─────────────────────────
        print(f"\n📝 [阶段8] 生成Markdown报告...")
        report_content = self.reporter.generate(final_items, self.stats)
        report_path = self.reporter.save(report_content, today)
        print(f"   报告已保存: {report_path}")

        # 保存报告元数据
        self.db.save_report_meta(
            report_date=today,
            file_path=report_path,
            total_items=len(final_items),
            sources_used=len(used_sources),
            nju_items=nju_count,
            github_items=github_count,
            categories=",".join(domain_counts.keys()),
        )

        # ── 清理缓存 ────────────────────────────────
        self._cleanup()

        print(f"\n✨ 全部完成! 耗时 {total_elapsed:.1f}s")
        print(f"   📊 报告: {report_path}")
        print(f"   📦 数据库: {self.db.conn.execute('SELECT COUNT(*) FROM history').fetchone()[0]} 条历史记录")

        return report_path

    def _cleanup(self):
        """清理运行时缓存（不删除报告）"""
        # SQLite WAL checkpoint (压缩wal文件)
        try:
            self.db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass

    def _load_sources(self) -> list[dict]:
        """加载信息源配置"""
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("sources", [])


def main():
    parser = argparse.ArgumentParser(description="🔥 AI技术热点日报爬虫")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument("--no-proxy", action="store_true", help="不使用代理")
    parser.add_argument("--report-only", action="store_true", help="仅从数据库生成报告(不抓取)")
    parser.add_argument("--stats", action="store_true", help="显示数据库统计")
    args = parser.parse_args()

    if args.no_proxy:
        import config
        config.USE_PROXY = False
        config.PROXIES = None

    if args.stats:
        db = Database()
        print("📊 数据库统计:")
        print(f"   历史记录: {db.conn.execute('SELECT COUNT(*) FROM history').fetchone()[0]} 条")
        print(f"   发现网站: {db.conn.execute('SELECT COUNT(*) FROM discovered_sites').fetchone()[0]} 个")
        stats = db.get_source_stats()
        if stats:
            print(f"\n   源站状态:")
            for s in stats[:10]:
                print(f"     {s['source_name']}: 成功率 {s['success_rate']:.0%}, {s['total_fetches']}次")
        db.close()
        return

    if args.report_only:
        db = Database()
        reporter = Reporter()
        today = datetime.date.today().isoformat()
        rows = db.conn.execute(
            "SELECT * FROM history WHERE report_date = ? ORDER BY relevance_score DESC",
            (today,)
        ).fetchall()
        if not rows:
            print(f"❌ 今天 ({today}) 没有抓取记录，请先运行抓取")
            db.close()
            return
        items = [dict(r) for r in rows]
        stats = {
            "total_fetched": len(items), "after_dedup": len(items),
            "total_items": len(items), "sources_used": len(set(it.get("source_name", "") for it in items)),
            "nju_items": sum(1 for it in items if it.get("is_nju")),
            "github_items": sum(1 for it in items if it.get("is_github")),
            "discovered_sites": 0, "domain_counts": {}, "elapsed_seconds": 0,
        }
        content = reporter.generate(items, stats)
        path = reporter.save(content, today)
        print(f"📝 报告已生成: {path}")
        db.close()
        return

    # 正常运行
    crawler = AIHotspotCrawler(verbose=args.verbose or True)
    try:
        asyncio.run(crawler.run())
        crawler.db.close()
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        crawler.db.close()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")
        traceback.print_exc()
        crawler.db.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
