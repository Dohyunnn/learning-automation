"""GitHub 활동 데이터 수집기.

GITHUB_TOKEN 환경변수가 없으면 mock 데이터를 반환한다.
"""
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MOCK_GITHUB_DATA: dict[str, Any] = {
    "username": "mock_user",
    "repos": [
        {
            "name": "fastapi-demo",
            "description": "FastAPI REST API demo project",
            "languages": {"Python": 8500, "Dockerfile": 200},
            "stars": 12,
            "recent_commits": [
                "Add async endpoint for user management",
                "Implement JWT authentication",
                "Add pytest test suite",
            ],
        },
        {
            "name": "langchain-experiments",
            "description": "LLM experiments with LangChain",
            "languages": {"Python": 5200, "Jupyter Notebook": 1200},
            "stars": 5,
            "recent_commits": [
                "Add RAG pipeline with FAISS",
                "Implement custom tool calling",
            ],
        },
        {
            "name": "data-pipeline",
            "description": "ETL pipeline with pandas",
            "languages": {"Python": 3800},
            "stars": 2,
            "recent_commits": [
                "Optimize DataFrame memory usage",
                "Add S3 connector",
            ],
        },
    ],
    "top_languages": ["Python", "Dockerfile", "Jupyter Notebook"],
    "total_repos": 3,
    "total_commits_last_month": 45,
}


class GitHubCollector:
    """GitHub REST API v3 를 통해 사용자 활동 데이터를 수집한다."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self._use_mock = not bool(self.token)
        if self._use_mock:
            logger.warning("GITHUB_TOKEN 없음 → mock 데이터 사용")

    async def collect(self, username: str | None = None) -> dict[str, Any]:
        """GitHub 활동 데이터를 수집한다.

        Returns:
            dict with keys: username, repos, top_languages,
                            total_repos, total_commits_last_month
        """
        if self._use_mock:
            return MOCK_GITHUB_DATA

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            try:
                # 사용자 정보
                user_resp = await client.get(f"{self.BASE_URL}/user")
                user_resp.raise_for_status()
                user = user_resp.json()
                uname = username or user["login"]

                # 레포지토리 목록
                repos_resp = await client.get(
                    f"{self.BASE_URL}/users/{uname}/repos",
                    params={"sort": "updated", "per_page": 20},
                )
                repos_resp.raise_for_status()
                repos_raw = repos_resp.json()

                repos = []
                language_counter: dict[str, int] = {}
                for repo in repos_raw[:20]:
                    # 언어 정보
                    lang_resp = await client.get(repo["languages_url"])
                    languages = lang_resp.json() if lang_resp.status_code == 200 else {}
                    for lang, bytes_ in languages.items():
                        language_counter[lang] = language_counter.get(lang, 0) + bytes_

                    # 최근 커밋 메시지
                    commits_resp = await client.get(
                        f"{self.BASE_URL}/repos/{uname}/{repo['name']}/commits",
                        params={"per_page": 10},
                    )
                    recent_commits = []
                    if commits_resp.status_code == 200:
                        for c in commits_resp.json()[:10]:
                            msg = c.get("commit", {}).get("message", "").splitlines()[0]
                            recent_commits.append(msg)

                    repos.append(
                        {
                            "name": repo["name"],
                            "description": repo.get("description") or "",
                            "languages": languages,
                            "stars": repo.get("stargazers_count", 0),
                            "recent_commits": recent_commits,
                        }
                    )

                top_languages = sorted(
                    language_counter.keys(),
                    key=lambda l: language_counter[l],
                    reverse=True,
                )[:5]

                return {
                    "username": uname,
                    "repos": repos,
                    "top_languages": top_languages,
                    "total_repos": len(repos),
                    "total_commits_last_month": sum(
                        len(r["recent_commits"]) for r in repos
                    ),
                }

            except httpx.HTTPError as e:
                logger.error("GitHub API 오류: %s — mock 데이터로 대체", e)
                return MOCK_GITHUB_DATA
