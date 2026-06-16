"""
GitHub Trending + Topics 抓取器
"""

import asyncio
from bs4 import BeautifulSoup
from crawlers.base import BaseCrawler
from config import MAX_ITEMS_PER_GITHUB, GITHUB_TOKEN
from processors.lamda_matcher import check_nju


class GitHubFetcher(BaseCrawler):
    """GitHub 热点项目抓取"""

    TRENDING_URL = "https://github.com/trending?since=daily"
    TRENDING_PYTHON_URL = "https://github.com/trending/python?since=daily"
    SEARCH_URL = "https://api.github.com/search/repositories"
    TOPICS_URL = "https://api.github.com/repos/{owner}/{repo}/topics"

    async def crawl(self) -> list[dict]:
        """并行抓取 GitHub 多源数据"""
        results = []

        # 并行抓取
        trending, trending_py, api_repos = await asyncio.gather(
            self._fetch_trending(self.TRENDING_URL, "GitHub Trending"),
            self._fetch_trending(self.TRENDING_PYTHON_URL, "GitHub Trending Python"),
            self._fetch_api_repos(),
            return_exceptions=True,
        )

        if isinstance(trending, list):
            results.extend(trending)
        if isinstance(trending_py, list):
            results.extend(trending_py)
        if isinstance(api_repos, list):
            results.extend(api_repos)

        return results

    async def _fetch_trending(self, url: str, source_name: str) -> list[dict]:
        """抓取 GitHub Trending 页面"""
        try:
            html = await self.fetch(url)
            if not html:
                return []

            soup = BeautifulSoup(html, "lxml")
            items = []
            repos = soup.select("article.Box-row")[:MAX_ITEMS_PER_GITHUB]

            for repo in repos:
                # 仓库名
                h2 = repo.select_one("h2 a")
                if not h2:
                    continue

                # 从href提取 owner/repo
                href = h2.get("href", "").strip()
                full_name = href.strip("/")
                title = " ".join(h2.stripped_strings)

                # 描述
                desc_el = repo.select_one("p.my-1")
                summary = desc_el.get_text(strip=True) if desc_el else ""

                # 语言
                lang_el = repo.select_one("[itemprop='programmingLanguage']")
                language = lang_el.get_text(strip=True) if lang_el else ""

                # Stars / Forks
                stars_el = repo.select_one(f"a[href='/{full_name}/stargazers']")
                forks_el = repo.select_one(f"a[href='/{full_name}/forks']")
                stars = stars_el.get_text(strip=True) if stars_el else ""
                forks = forks_el.get_text(strip=True) if forks_el else ""

                # 今日star数
                today_stars_el = repo.select_one("span.float-sm-right")
                today_stars = today_stars_el.get_text(strip=True) if today_stars_el else ""

                url_full = f"https://github.com{href}"

                # LAMDA成员 + NJU精确匹配
                all_text = title + " " + summary
                is_nju = check_nju(all_text)

                items.append(self.make_item(
                    url=url_full,
                    title=title,
                    summary=f"[{language}] ⭐{stars} {today_stars} — {summary}"[:500],
                    source_name=source_name,
                    source_type="web",
                    category="code",
                    is_nju=is_nju,
                    language=language,
                    stars=stars,
                    forks=forks,
                    today_stars=today_stars,
                    platform="github",
                    is_github=True,
                ))

            return items

        except Exception as e:
            return []

    async def _fetch_api_repos(self) -> list[dict]:
        """通过 GitHub API 搜索 AI 相关热门仓库 (带Token认证)"""
        queries = [
            ("AI Agent framework stars:>100", "GitHub Search: AI Agent"),
            ("LLM tool use stars:>100", "GitHub Search: LLM Tools"),
            ("machine learning framework stars:>500", "GitHub Search: ML Framework"),
            ("reinforcement learning environment stars:>50", "GitHub Search: RL"),
            ("Nanjing University artificial intelligence", "GitHub Search: NJU"),
        ]

        headers = {}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = "2022-11-28"

        items = []
        for query, label in queries:
            try:
                result = await self.fetch_json(
                    f"{self.SEARCH_URL}?q={query}&sort=stars&order=desc&per_page=5",
                    headers=headers,
                )
                if not result or "items" not in result:
                    continue

                for repo in result["items"]:
                    desc = repo.get("description", "") or ""
                    is_nju = check_nju(repo.get("full_name", "") + " " + desc)

                    items.append(self.make_item(
                        url=repo.get("html_url", ""),
                        title=repo.get("full_name", ""),
                        summary=f"[{repo.get('language', '')}] ⭐{repo.get('stargazers_count', 0)} — {desc}"[:500],
                        source_name=label,
                        source_type="api",
                        category="code",
                        is_nju=is_nju,
                        language=repo.get("language", ""),
                        stars=str(repo.get("stargazers_count", 0)),
                        forks=str(repo.get("forks_count", 0)),
                        platform="github",
                        is_github=True,
                    ))

            except Exception:
                continue

        return items
