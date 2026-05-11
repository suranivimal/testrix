from dataclasses import asdict

from agents.llm_client import LLMClient
from qa.models import RequirementModel
from utils.file_io import read_requirements_file


class RequirementAnalyzer:
    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    async def analyze(self, requirement_path: str) -> RequirementModel:
        raw_text = read_requirements_file(requirement_path)
        prompt = f"""
Extract structured QA requirements from the following document text.
Return strict JSON with keys:
features, acceptance_criteria, functional_flows, validation_logic, edge_cases, business_expectations.

Document:
{raw_text[:12000]}
"""
        parsed = await self.llm_client.complete_json(
            system_prompt="You are a senior QA requirement analyst.",
            user_prompt=prompt,
        )

        model = RequirementModel(
            source_path=requirement_path,
            features=parsed.get("features", []),
            acceptance_criteria=parsed.get("acceptance_criteria", []),
            functional_flows=parsed.get("functional_flows", []),
            validation_logic=parsed.get("validation_logic", []),
            edge_cases=parsed.get("edge_cases", []),
            business_expectations=parsed.get("business_expectations", []),
        )
        _ = asdict(model)
        return model