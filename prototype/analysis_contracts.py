"""Wire responses group related extraction work into the existing seven calls.

Core E5 DTOs remain owned by the domain layer; no new display inference is done here.
"""
from .contracts import Facts, Evaluation
from .candidate_profile import CandidateProfile, Conditions


class ResumeAnalysis(Facts):
    profile: CandidateProfile


class VacancyAnalysis(Evaluation):
    conditions: Conditions
