from nanimai_platform.cmd.server.utils.dtobase import DTOBase
from nanimai_platform.domain.scalar.scalars import CandidateID, VacancyID


class FactorAnalysisCompleteRequestDTO(DTOBase):
    candidate_id: CandidateID


class RebalanceVacancyCandidateRequestDTO(DTOBase):
    new_threshold: float
    vacancy_id: VacancyID
