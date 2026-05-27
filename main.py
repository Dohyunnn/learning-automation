"""CLI 진입점.

사용 예시:
    python main.py --topic "FastAPI" --depth intermediate
    python main.py --topic "LangGraph" --depth advanced --no-confluence
"""
import asyncio
import logging
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="learning-automation",
    help="AI 기반 개인 맞춤 학습 커리큘럼 자동 생성 시스템",
)
console = Console()


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="학습 주제 (예: 'FastAPI')"),
    depth: str = typer.Option(
        "intermediate",
        "--depth",
        "-d",
        help="학습 수준: beginner | intermediate | advanced",
    ),
    no_confluence: bool = typer.Option(
        False, "--no-confluence", help="Confluence 업로드 건너뜀"
    ),
    log_level: str = typer.Option("INFO", "--log-level", help="로그 레벨"),
) -> None:
    """학습 커리큘럼을 자동 생성한다."""
    setup_logging(log_level)

    if depth not in ("beginner", "intermediate", "advanced"):
        console.print(
            "[red]오류: depth는 beginner | intermediate | advanced 중 하나여야 합니다.[/red]"
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold cyan]🤖 AI 학습 자동화 시스템[/bold cyan]\n\n"
            f"주제: [green]{topic}[/green]\n"
            f"수준: [yellow]{depth}[/yellow]",
            title="learning-automation",
            border_style="cyan",
        )
    )

    asyncio.run(_run_pipeline(topic, depth, no_confluence))


async def _run_pipeline(topic: str, depth: str, no_confluence: bool) -> None:
    from graph.builder import compile_graph

    if no_confluence:
        import os
        os.environ["CONFLUENCE_BASE_URL"] = ""

    initial_state = {
        "topic": topic,
        "depth": depth,
        "github_data": None,
        "confluence_history": None,
        "user_profile": None,
        "curriculum": None,
        "resources": None,
        "validation_result": None,
        "retry_count": 0,
        "final_markdown": None,
        "confluence_page_id": None,
        "errors": [],
    }

    graph = compile_graph()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("파이프라인 실행 중...", total=None)
        result = await graph.ainvoke(initial_state)
        progress.update(task, completed=True)

    # 결과 출력
    validation = result.get("validation_result") or {}
    passed = validation.get("passed", False)
    score = validation.get("score", 0.0)

    if passed:
        console.print(f"\n[bold green]✅ 검증 통과[/bold green] (점수: {score:.0%})")
    else:
        console.print(f"\n[bold yellow]⚠️ 검증 미통과[/bold yellow] (점수: {score:.0%})")

    if result.get("final_markdown"):
        console.print("[green]📄 마크다운 파일 저장 완료[/green]")

    if result.get("confluence_page_id"):
        console.print(
            f"[green]📝 Confluence 페이지 생성: {result['confluence_page_id']}[/green]"
        )

    errors = result.get("errors") or []
    if errors:
        console.print("\n[yellow]⚠️ 경고/오류:[/yellow]")
        for err in errors:
            console.print(f"  - {err}")


if __name__ == "__main__":
    app()
