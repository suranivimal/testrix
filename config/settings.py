import os
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    claude_api_key: str = os.getenv("CLAUDE_API_KEY", "")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")

    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")
    llm_model: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))

    figma_api_token: str = os.getenv("FIGMA_API_TOKEN", "")
    browser_headless: bool = os.getenv("BROWSER_HEADLESS", "true").lower() == "true"
    browser_timeout_ms: int = int(os.getenv("BROWSER_TIMEOUT_MS", "30000"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    visual_diff_threshold: float = float(os.getenv("VISUAL_DIFF_THRESHOLD", "0.22"))
    visual_diff_page_thresholds_raw: str = os.getenv("VISUAL_DIFF_PAGE_THRESHOLDS", "{}")
    strict_accessibility: bool = os.getenv("STRICT_ACCESSIBILITY", "false").lower() == "true"

    target_url: str = os.getenv("TARGET_URL", "")
    figma_url: str = os.getenv("FIGMA_URL", "")
    requirements_path: str = os.getenv("REQUIREMENTS_PATH", "")
    output_dir: str = os.getenv("OUTPUT_DIR", "artifacts")

    screenshot_dir: Path = field(init=False)
    report_dir: Path = field(init=False)
    visual_diff_page_thresholds: dict[str, float] = field(init=False)

    def __post_init__(self) -> None:
        root = Path(self.output_dir)
        self.screenshot_dir = root / "screenshots"
        self.report_dir = root / "reports"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.visual_diff_page_thresholds = self._parse_page_thresholds()

    def _parse_page_thresholds(self) -> dict[str, float]:
        try:
            parsed = json.loads(self.visual_diff_page_thresholds_raw or "{}")
            if not isinstance(parsed, dict):
                return {}
            thresholds: dict[str, float] = {}
            for key, value in parsed.items():
                try:
                    thresholds[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue
            return thresholds
        except json.JSONDecodeError:
            return {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
