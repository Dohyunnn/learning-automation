"""마크다운 파일 출력기."""
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

OUTPUT_DIR = "output"


class MarkdownWriter:
    """검증된 커리큘럼을 마크다운으로 렌더링·저장한다."""

    def write(
        self,
        topic: str,
        depth: str,
        curriculum: dict[str, Any],
        resources: list[dict[str, Any]],
        validation_result: dict[str, Any],
        save: bool = True,
    ) -> str:
        """마크다운 문자열을 생성하고 파일로 저장한다."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = topic.lower().replace(" ", "_")

        lines: list[str] = []

        # ── 헤더 ──────────────────────────────────────────────────────────
        lines += [
            f"# {curriculum.get('title', f'{topic} 학습 커리큘럼')}",
            "",
            f"> **수준**: {depth}  ",
            f"> **총 학습 시간**: {curriculum.get('total_duration_hours', '?')}시간  ",
            f"> **생성일**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            f"> **검증 점수**: {validation_result.get('score', 0):.0%}",
            "",
            "---",
            "",
        ]

        # ── 개요 ──────────────────────────────────────────────────────────
        lines += [
            "## 📋 개요",
            "",
            curriculum.get("overview", ""),
            "",
        ]

        # ── 학습 목표 ─────────────────────────────────────────────────────
        objectives = curriculum.get("objectives", [])
        if objectives:
            lines += ["## 🎯 학습 목표", ""]
            for obj in objectives:
                lines.append(f"- {obj}")
            lines.append("")

        # ── 사전 요구사항 ─────────────────────────────────────────────────
        prerequisites = curriculum.get("prerequisites", [])
        if prerequisites:
            lines += ["## ⚙️ 사전 요구사항", ""]
            for pre in prerequisites:
                lines.append(f"- {pre}")
            lines.append("")

        # ── 커리큘럼 단계 ─────────────────────────────────────────────────
        stages = curriculum.get("stages", [])
        if stages:
            lines += ["## 📚 커리큘럼", ""]
            for stage in stages:
                lines += [
                    f"### Stage {stage.get('stage', '?')}: {stage.get('title', '')}",
                    "",
                    f"**예상 소요**: {stage.get('duration_hours', '?')}시간  ",
                    f"**완료 기준**: {stage.get('milestone', '')}",
                    "",
                    "**학습 주제:**",
                ]
                for t in stage.get("topics", []):
                    lines.append(f"- {t}")
                hands_on = stage.get("hands_on", "")
                if hands_on:
                    lines += ["", f"**실습 프로젝트:** {hands_on}"]
                lines.append("")

        # ── 참고 자료 ─────────────────────────────────────────────────────
        if resources:
            lines += ["## 🔗 참고 자료", ""]
            for r in resources:
                free_badge = "🆓" if r.get("is_free") else "💰"
                lines.append(
                    f"- {free_badge} **[{r.get('title', '')}]({r.get('url', '#')})** "
                    f"({r.get('type', '')} · {r.get('estimated_hours', '?')}h)  "
                )
                if r.get("description"):
                    lines.append(f"  {r['description']}")
            lines.append("")

        # ── 검증 결과 ─────────────────────────────────────────────────────
        lines += [
            "## ✅ 검증 결과",
            "",
            f"- **통과 여부**: {'✅ 통과' if validation_result.get('passed') else '❌ 미통과'}",
            f"- **점수**: {validation_result.get('score', 0):.0%}",
            f"- **할루시네이션 위험도**: {validation_result.get('hallucination_risk', 'unknown')}",
            "",
            validation_result.get("summary", ""),
            "",
        ]

        issues = validation_result.get("issues", [])
        if issues:
            lines += ["**발견된 이슈:**", ""]
            for issue in issues:
                lines.append(f"- ⚠️ {issue}")
            lines.append("")

        # ── 푸터 ──────────────────────────────────────────────────────────
        lines += [
            "---",
            "",
            "*이 문서는 AI 학습 자동화 시스템으로 자동 생성되었습니다.*",
            "",
        ]

        markdown = "\n".join(lines)

        if save:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            filepath = os.path.join(OUTPUT_DIR, f"{slug}_{depth}_{timestamp}.md")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(markdown)
            logger.info("[MarkdownWriter] 저장 완료: %s", filepath)

        return markdown
