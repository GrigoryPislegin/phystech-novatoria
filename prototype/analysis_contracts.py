"""Wire responses group related extraction work into the existing seven calls.

Core E5 DTOs remain owned by the domain layer; no new display inference is done here.
"""
from .contracts import Facts, Evaluation, Requirements, RequirementFactors
from .candidate_profile import CandidateProfile, Conditions


class ResumeAnalysis(Facts):
    profile: CandidateProfile


class RequirementsAnalysis(Requirements):
    # Existing replay/stored requirements may omit labels. The SDK's strict
    # schema requests this nullable field in the same requirements response.
    factors: RequirementFactors | None = None

    def validate_source(self, source):
        super().validate_source(source)
        if self.factors is not None:
            self.factors.validate_requirements(self)


class VacancyAnalysis(Evaluation):
    conditions: Conditions
