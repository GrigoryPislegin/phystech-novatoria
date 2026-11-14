"""Wire responses group resume extraction and joint per-vacancy analysis.

Core E5 DTOs remain owned by the domain layer; no new display inference is done here.
"""
from .contracts import Facts, Evaluation, Requirements, RequirementFactors, StrictModel
from .candidate_profile import CandidateProfile, Conditions
from pydantic import PrivateAttr


class ResumeAnalysis(Facts):
    profile: CandidateProfile


class RequirementsAnalysis(Requirements):
    # Existing replay/stored requirements may omit labels. The SDK's strict
    # schema requests this nullable field in the same requirements response.
    factors: RequirementFactors | None = None
    _contract_warnings: list[dict[str, str]] = PrivateAttr(default_factory=list)

    def without_unverified_mandatory(self, source):
        """Discard unsupported optional markers, never repair a requirement quote.

        Called only after the complete provider response passed privacy. The
        remaining DTO must satisfy the unchanged core/source contract; a bad
        requirement, duplicate or factor reference still rejects the response.
        """
        result = self.model_copy(deep=True)
        for item in result.items:
            marker = item.mandatory_quote
            if marker is not None and (marker not in source or len(marker.strip()) < 8 or item.quote not in marker):
                item.mandatory_quote = None
                result._contract_warnings.append({'code':'mandatory_status_unconfirmed', 'requirement_id':item.id})
        result.validate_source(source)
        return result

    def validate_source(self, source):
        super().validate_source(source)
        if self.factors is not None:
            self.factors.validate_requirements(self)


class VacancyAnalysis(Evaluation):
    conditions: Conditions


class JointAnalysis(StrictModel):
    requirements: RequirementsAnalysis
    evaluation: VacancyAnalysis
