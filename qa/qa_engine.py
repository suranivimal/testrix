from PIL import Image, ImageChops, ImageStat

from qa.models import BrowserObservation, FigmaBaseline, Finding, QAEvaluation, RequirementModel


class QAEngine:
    def evaluate(
        self,
        requirements: RequirementModel,
        figma: FigmaBaseline | None,
        observations: list[BrowserObservation],
        visual_diff_threshold: float = 0.22,
        page_threshold_overrides: dict[str, float] | None = None,
    ) -> QAEvaluation:
        findings: list[Finding] = []
        coverage: list[str] = []
        missing_features: list[str] = []
        accessibility_gaps: list[str] = []
        responsive_issues: list[str] = []
        visual_mismatch_scores: dict[str, dict[str, float]] = {}
        accessibility_blocker_count = 0
        page_threshold_overrides = page_threshold_overrides or {}

        for feature in requirements.features:
            matched = any(feature.lower() in " ".join(obs.interaction_notes).lower() for obs in observations)
            if matched:
                coverage.append(feature)
            else:
                missing_features.append(feature)
                findings.append(
                    Finding(
                        title=f"Potential missing feature: {feature}",
                        category="requirement-coverage",
                        severity="high",
                        priority="P1",
                        evidence="Feature could not be confirmed during browser interactions.",
                    )
                )

        for obs in observations:
            if obs.error:
                findings.append(
                    Finding(
                        title=f"Navigation failure on {obs.page} ({obs.viewport})",
                        category="functional",
                        severity="critical",
                        priority="P0",
                        evidence=obs.error,
                        page=obs.page,
                    )
                )
            for err in obs.console_errors:
                findings.append(
                    Finding(
                        title=f"Console error on {obs.page} ({obs.viewport})",
                        category="functional",
                        severity="medium",
                        priority="P2",
                        evidence=err[:240],
                        page=obs.page,
                    )
                )
            for failure in obs.network_failures:
                findings.append(
                    Finding(
                        title=f"Network request failure on {obs.page} ({obs.viewport})",
                        category="functional",
                        severity="high",
                        priority="P1",
                        evidence=failure,
                        page=obs.page,
                    )
                )
            accessibility_gaps.extend(obs.accessibility_notes)
            for note in obs.accessibility_notes:
                lowered = note.lower()
                if "axe [critical]" in lowered or "axe [serious]" in lowered:
                    accessibility_blocker_count += 1

        by_page = {}
        for obs in observations:
            by_page.setdefault(obs.page, set()).add(obs.viewport)
        for page, viewports in by_page.items():
            if len(viewports) < 3:
                responsive_issues.append(f"Page {page} did not complete checks on all device classes.")
        visual_mismatch_scores = self._compute_visual_mismatch_scores(observations)
        for page, scores in visual_mismatch_scores.items():
            for viewport, score in scores.items():
                threshold = page_threshold_overrides.get(page, visual_diff_threshold)
                if score > threshold:
                    findings.append(
                        Finding(
                            title=f"High visual divergence on {page} ({viewport} vs desktop)",
                            category="ui",
                            severity="medium",
                            priority="P2",
                            evidence=f"Viewport visual mismatch score={score:.3f}, threshold={threshold:.3f}",
                            page=page,
                        )
                    )

        if figma:
            if not figma.components:
                findings.append(
                    Finding(
                        title="Figma extraction returned no component baseline",
                        category="ui",
                        severity="medium",
                        priority="P2",
                        evidence="Design baseline is incomplete, visual checks are lower confidence.",
                    )
                )
            if not figma.colors:
                findings.append(
                    Finding(
                        title="No color tokens parsed from Figma",
                        category="ui",
                        severity="low",
                        priority="P3",
                        evidence="Unable to validate brand color consistency from design baseline.",
                    )
                )

        return QAEvaluation(
            requirement_coverage=coverage,
            missing_features=missing_features,
            findings=findings,
            accessibility_gaps=accessibility_gaps,
            responsive_issues=responsive_issues,
            visual_mismatch_scores=visual_mismatch_scores,
            accessibility_blocker_count=accessibility_blocker_count,
        )

    def _compute_visual_mismatch_scores(self, observations: list[BrowserObservation]) -> dict[str, dict[str, float]]:
        by_page: dict[str, dict[str, str]] = {}
        for obs in observations:
            if obs.screenshot_path:
                by_page.setdefault(obs.page, {})[obs.viewport] = obs.screenshot_path

        results: dict[str, dict[str, float]] = {}
        for page, paths in by_page.items():
            desktop_path = paths.get("desktop")
            if not desktop_path:
                continue

            scores: dict[str, float] = {}
            with Image.open(desktop_path).convert("RGB") as desktop:
                for viewport in ("tablet", "mobile"):
                    candidate_path = paths.get(viewport)
                    if not candidate_path:
                        continue
                    with Image.open(candidate_path).convert("RGB") as candidate:
                        resized_candidate = candidate.resize(desktop.size)
                        diff = ImageChops.difference(desktop, resized_candidate)
                        stat = ImageStat.Stat(diff)
                        mean_delta = sum(stat.mean) / (len(stat.mean) * 255)
                        scores[viewport] = round(float(mean_delta), 4)

            if scores:
                results[page] = scores
        return results
