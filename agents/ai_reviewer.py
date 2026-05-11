from qa.models import FigmaBaseline, QAEvaluation, RequirementModel


class AIReviewer:
    def __init__(self, llm_client) -> None:
        self.llm_client = llm_client

    async def review(
        self,
        requirements: RequirementModel,
        figma: FigmaBaseline | None,
        qa_result: QAEvaluation,
        strict_accessibility: bool = False,
    ) -> dict:
        prompt = f"""
You are a Senior QA Lead and release reviewer.
Generate JSON keys:
- qa_observations: list[str]
- bug_summary: list[str]
- ux_analysis: list[str]
- recommendation: "GO" or "NO-GO"
- rationale: string

Inputs:
requirements_features={requirements.features}
acceptance_criteria={requirements.acceptance_criteria}
figma_components={(figma.components if figma else [])}
findings={[f"{item.severity}|{item.title}|{item.evidence}" for item in qa_result.findings]}
accessibility_gaps={qa_result.accessibility_gaps}
responsive_issues={qa_result.responsive_issues}
missing_features={qa_result.missing_features}
accessibility_blocker_count={qa_result.accessibility_blocker_count}
"""
        result = await self.llm_client.complete_json(
            system_prompt="Use GStack-style review rigor: clear, critical, and evidence-driven.",
            user_prompt=prompt,
        )
        if "recommendation" not in result:
            result["recommendation"] = "NO-GO" if any(f.severity in {"critical", "high"} for f in qa_result.findings) else "GO"
        if strict_accessibility and qa_result.accessibility_blocker_count > 0:
            result["recommendation"] = "NO-GO"
            existing_rationale = result.get("rationale", "")
            result["rationale"] = (
                f"{existing_rationale} Strict accessibility mode is enabled and blocker-level accessibility issues were found."
            ).strip()
        return result