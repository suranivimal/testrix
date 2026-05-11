from dataclasses import dataclass, field


@dataclass(slots=True)
class RequirementModel:
    source_path: str
    features: list[str]
    acceptance_criteria: list[str]
    functional_flows: list[str]
    validation_logic: list[str]
    edge_cases: list[str]
    business_expectations: list[str]


@dataclass(slots=True)
class FigmaBaseline:
    source_url: str
    typography: list[str]
    colors: list[str]
    components: list[str]
    layout_structure: list[str]
    spacing: list[str]
    buttons: list[str]
    responsive_structure: list[str]


@dataclass(slots=True)
class BrowserObservation:
    page: str
    url: str
    viewport: str
    screenshot_path: str | None
    console_errors: list[str] = field(default_factory=list)
    network_failures: list[str] = field(default_factory=list)
    interaction_notes: list[str] = field(default_factory=list)
    accessibility_notes: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class Finding:
    title: str
    category: str
    severity: str
    priority: str
    evidence: str
    page: str | None = None


@dataclass(slots=True)
class QAEvaluation:
    requirement_coverage: list[str]
    missing_features: list[str]
    findings: list[Finding]
    accessibility_gaps: list[str]
    responsive_issues: list[str]
    visual_mismatch_scores: dict[str, dict[str, float]]
    accessibility_blocker_count: int
