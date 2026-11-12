from typing import ClassVar, final

import hharon.pkg.hhapi.dictionaries as hh
import hharon_api.v1.headhunter_pb2 as proto


@final
class ResumeAccessTypeMapper:
    RESUME_ACCESS_TYPE_PROTO: ClassVar[dict[hh.ResumeAccessTypeEnum, proto.ResumeAccessType.ValueType]] = {
        hh.ResumeAccessTypeEnum.NO_ONE: proto.RESUME_ACCESS_TYPE_NO_ONE,
        hh.ResumeAccessTypeEnum.WHITELIST: proto.RESUME_ACCESS_TYPE_WHITELIST,
        hh.ResumeAccessTypeEnum.BLACKLIST: proto.RESUME_ACCESS_TYPE_BLACKLIST,
        hh.ResumeAccessTypeEnum.CLIENTS: proto.RESUME_ACCESS_TYPE_CLIENTS,
        hh.ResumeAccessTypeEnum.EVERYONE: proto.RESUME_ACCESS_TYPE_EVERYONE,
        hh.ResumeAccessTypeEnum.DIRECT: proto.RESUME_ACCESS_TYPE_DIRECT,
    }
    RESUME_ACCESS_TYPE_PYTHON: ClassVar[dict[proto.ResumeAccessType.ValueType, hh.ResumeAccessTypeEnum]] = {
        proto.RESUME_ACCESS_TYPE_NO_ONE: hh.ResumeAccessTypeEnum.NO_ONE,
        proto.RESUME_ACCESS_TYPE_WHITELIST: hh.ResumeAccessTypeEnum.WHITELIST,
        proto.RESUME_ACCESS_TYPE_BLACKLIST: hh.ResumeAccessTypeEnum.BLACKLIST,
        proto.RESUME_ACCESS_TYPE_CLIENTS: hh.ResumeAccessTypeEnum.CLIENTS,
        proto.RESUME_ACCESS_TYPE_EVERYONE: hh.ResumeAccessTypeEnum.EVERYONE,
        proto.RESUME_ACCESS_TYPE_DIRECT: hh.ResumeAccessTypeEnum.DIRECT,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeAccessTypeEnum) -> proto.ResumeAccessType.ValueType:
        return cls.RESUME_ACCESS_TYPE_PROTO.get(value, proto.RESUME_ACCESS_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeAccessType.ValueType) -> hh.ResumeAccessTypeEnum | None:
        return cls.RESUME_ACCESS_TYPE_PYTHON.get(value, None)


@final
class VacancySearchOrderMapper:
    VACANCY_SEARCH_ORDER_PROTO: ClassVar[dict[hh.VacancySearchOrderEnum, proto.VacancySearchOrder.ValueType]] = {
        hh.VacancySearchOrderEnum.PUBLICATION_TIME: proto.VACANCY_SEARCH_ORDER_PUBLICATION_TIME,
        hh.VacancySearchOrderEnum.SALARY_DESC: proto.VACANCY_SEARCH_ORDER_SALARY_DESC,
        hh.VacancySearchOrderEnum.SALARY_ASC: proto.VACANCY_SEARCH_ORDER_SALARY_ASC,
        hh.VacancySearchOrderEnum.RELEVANCE: proto.VACANCY_SEARCH_ORDER_RELEVANCE,
        hh.VacancySearchOrderEnum.DISTANCE: proto.VACANCY_SEARCH_ORDER_DISTANCE,
    }
    VACANCY_SEARCH_ORDER_PYTHON: ClassVar[dict[proto.VacancySearchOrder.ValueType, hh.VacancySearchOrderEnum]] = {
        proto.VACANCY_SEARCH_ORDER_PUBLICATION_TIME: hh.VacancySearchOrderEnum.PUBLICATION_TIME,
        proto.VACANCY_SEARCH_ORDER_SALARY_DESC: hh.VacancySearchOrderEnum.SALARY_DESC,
        proto.VACANCY_SEARCH_ORDER_SALARY_ASC: hh.VacancySearchOrderEnum.SALARY_ASC,
        proto.VACANCY_SEARCH_ORDER_RELEVANCE: hh.VacancySearchOrderEnum.RELEVANCE,
        proto.VACANCY_SEARCH_ORDER_DISTANCE: hh.VacancySearchOrderEnum.DISTANCE,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancySearchOrderEnum) -> proto.VacancySearchOrder.ValueType:
        return cls.VACANCY_SEARCH_ORDER_PROTO.get(value, proto.VACANCY_SEARCH_ORDER_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancySearchOrder.ValueType) -> hh.VacancySearchOrderEnum | None:
        return cls.VACANCY_SEARCH_ORDER_PYTHON.get(value, None)


@final
class VacancySearchFieldsMapper:
    VACANCY_SEARCH_FIELDS_PROTO: ClassVar[dict[hh.VacancySearchFieldsEnum, proto.VacancySearchFields.ValueType]] = {
        hh.VacancySearchFieldsEnum.NAME: proto.VACANCY_SEARCH_FIELDS_NAME,
        hh.VacancySearchFieldsEnum.COMPANY_NAME: proto.VACANCY_SEARCH_FIELDS_COMPANY_NAME,
        hh.VacancySearchFieldsEnum.DESCRIPTION: proto.VACANCY_SEARCH_FIELDS_DESCRIPTION,
    }
    VACANCY_SEARCH_FIELDS_PYTHON: ClassVar[dict[proto.VacancySearchFields.ValueType, hh.VacancySearchFieldsEnum]] = {
        proto.VACANCY_SEARCH_FIELDS_NAME: hh.VacancySearchFieldsEnum.NAME,
        proto.VACANCY_SEARCH_FIELDS_COMPANY_NAME: hh.VacancySearchFieldsEnum.COMPANY_NAME,
        proto.VACANCY_SEARCH_FIELDS_DESCRIPTION: hh.VacancySearchFieldsEnum.DESCRIPTION,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancySearchFieldsEnum) -> proto.VacancySearchFields.ValueType:
        return cls.VACANCY_SEARCH_FIELDS_PROTO.get(value, proto.VACANCY_SEARCH_FIELDS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancySearchFields.ValueType) -> hh.VacancySearchFieldsEnum | None:
        return cls.VACANCY_SEARCH_FIELDS_PYTHON.get(value, None)


@final
class VacancySearchEmploymentFormMapper:
    VACANCY_SEARCH_EMPLOYMENT_FORM_PROTO: ClassVar[
        dict[hh.VacancySearchEmploymentFormEnum, proto.VacancySearchEmploymentForm.ValueType]
    ] = {
        hh.VacancySearchEmploymentFormEnum.FULL: proto.VACANCY_SEARCH_EMPLOYMENT_FORM_FULL,
        hh.VacancySearchEmploymentFormEnum.PART: proto.VACANCY_SEARCH_EMPLOYMENT_FORM_PART,
        hh.VacancySearchEmploymentFormEnum.PROJECT: proto.VACANCY_SEARCH_EMPLOYMENT_FORM_PROJECT,
        hh.VacancySearchEmploymentFormEnum.FLY_IN_FLY_OUT: proto.VACANCY_SEARCH_EMPLOYMENT_FORM_FLY_IN_FLY_OUT,
    }
    VACANCY_SEARCH_EMPLOYMENT_FORM_PYTHON: ClassVar[
        dict[proto.VacancySearchEmploymentForm.ValueType, hh.VacancySearchEmploymentFormEnum]
    ] = {
        proto.VACANCY_SEARCH_EMPLOYMENT_FORM_FULL: hh.VacancySearchEmploymentFormEnum.FULL,
        proto.VACANCY_SEARCH_EMPLOYMENT_FORM_PART: hh.VacancySearchEmploymentFormEnum.PART,
        proto.VACANCY_SEARCH_EMPLOYMENT_FORM_PROJECT: hh.VacancySearchEmploymentFormEnum.PROJECT,
        proto.VACANCY_SEARCH_EMPLOYMENT_FORM_FLY_IN_FLY_OUT: hh.VacancySearchEmploymentFormEnum.FLY_IN_FLY_OUT,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancySearchEmploymentFormEnum) -> proto.VacancySearchEmploymentForm.ValueType:
        return cls.VACANCY_SEARCH_EMPLOYMENT_FORM_PROTO.get(value, proto.VACANCY_SEARCH_EMPLOYMENT_FORM_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancySearchEmploymentForm.ValueType) -> hh.VacancySearchEmploymentFormEnum | None:
        return cls.VACANCY_SEARCH_EMPLOYMENT_FORM_PYTHON.get(value, None)


@final
class GenderMapper:
    GENDER_PROTO: ClassVar[dict[hh.GenderEnum, proto.Gender.ValueType]] = {
        hh.GenderEnum.MALE: proto.GENDER_MALE,
        hh.GenderEnum.FEMALE: proto.GENDER_FEMALE,
    }
    GENDER_PYTHON: ClassVar[dict[proto.Gender.ValueType, hh.GenderEnum]] = {
        proto.GENDER_MALE: hh.GenderEnum.MALE,
        proto.GENDER_FEMALE: hh.GenderEnum.FEMALE,
    }

    @classmethod
    def to_proto(cls, value: hh.GenderEnum) -> proto.Gender.ValueType:
        return cls.GENDER_PROTO.get(value, proto.GENDER_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.Gender.ValueType) -> hh.GenderEnum | None:
        return cls.GENDER_PYTHON.get(value, None)


@final
class PreferredContactTypeMapper:
    PREFERRED_CONTACT_TYPE_PROTO: ClassVar[dict[hh.PreferredContactTypeEnum, proto.PreferredContactType.ValueType]] = {
        hh.PreferredContactTypeEnum.HOME: proto.PREFERRED_CONTACT_TYPE_HOME,
        hh.PreferredContactTypeEnum.WORK: proto.PREFERRED_CONTACT_TYPE_WORK,
        hh.PreferredContactTypeEnum.CELL: proto.PREFERRED_CONTACT_TYPE_CELL,
        hh.PreferredContactTypeEnum.EMAIL: proto.PREFERRED_CONTACT_TYPE_EMAIL,
    }
    PREFERRED_CONTACT_TYPE_PYTHON: ClassVar[dict[proto.PreferredContactType.ValueType, hh.PreferredContactTypeEnum]] = {
        proto.PREFERRED_CONTACT_TYPE_HOME: hh.PreferredContactTypeEnum.HOME,
        proto.PREFERRED_CONTACT_TYPE_WORK: hh.PreferredContactTypeEnum.WORK,
        proto.PREFERRED_CONTACT_TYPE_CELL: hh.PreferredContactTypeEnum.CELL,
        proto.PREFERRED_CONTACT_TYPE_EMAIL: hh.PreferredContactTypeEnum.EMAIL,
    }

    @classmethod
    def to_proto(cls, value: hh.PreferredContactTypeEnum) -> proto.PreferredContactType.ValueType:
        return cls.PREFERRED_CONTACT_TYPE_PROTO.get(value, proto.PREFERRED_CONTACT_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.PreferredContactType.ValueType) -> hh.PreferredContactTypeEnum | None:
        return cls.PREFERRED_CONTACT_TYPE_PYTHON.get(value, None)


@final
class TravelTimeMapper:
    TRAVEL_TIME_PROTO: ClassVar[dict[hh.TravelTimeEnum, proto.TravelTime.ValueType]] = {
        hh.TravelTimeEnum.ANY: proto.TRAVEL_TIME_ANY,
        hh.TravelTimeEnum.LESS_THAN_HOUR: proto.TRAVEL_TIME_LESS_THAN_HOUR,
        hh.TravelTimeEnum.FROM_HOUR_TO_ONE_AND_HALF: proto.TRAVEL_TIME_FROM_HOUR_TO_ONE_AND_HALF,
    }
    TRAVEL_TIME_PYTHON: ClassVar[dict[proto.TravelTime.ValueType, hh.TravelTimeEnum]] = {
        proto.TRAVEL_TIME_ANY: hh.TravelTimeEnum.ANY,
        proto.TRAVEL_TIME_LESS_THAN_HOUR: hh.TravelTimeEnum.LESS_THAN_HOUR,
        proto.TRAVEL_TIME_FROM_HOUR_TO_ONE_AND_HALF: hh.TravelTimeEnum.FROM_HOUR_TO_ONE_AND_HALF,
    }

    @classmethod
    def to_proto(cls, value: hh.TravelTimeEnum) -> proto.TravelTime.ValueType:
        return cls.TRAVEL_TIME_PROTO.get(value, proto.TRAVEL_TIME_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.TravelTime.ValueType) -> hh.TravelTimeEnum | None:
        return cls.TRAVEL_TIME_PYTHON.get(value, None)


@final
class RelocationTypeMapper:
    RELOCATION_TYPE_PROTO: ClassVar[dict[hh.RelocationTypeEnum, proto.RelocationType.ValueType]] = {
        hh.RelocationTypeEnum.NO_RELOCATION: proto.RELOCATION_TYPE_NO_RELOCATION,
        hh.RelocationTypeEnum.RELOCATION_POSSIBLE: proto.RELOCATION_TYPE_RELOCATION_POSSIBLE,
        hh.RelocationTypeEnum.RELOCATION_DESIRABLE: proto.RELOCATION_TYPE_RELOCATION_DESIRABLE,
    }
    RELOCATION_TYPE_PYTHON: ClassVar[dict[proto.RelocationType.ValueType, hh.RelocationTypeEnum]] = {
        proto.RELOCATION_TYPE_NO_RELOCATION: hh.RelocationTypeEnum.NO_RELOCATION,
        proto.RELOCATION_TYPE_RELOCATION_POSSIBLE: hh.RelocationTypeEnum.RELOCATION_POSSIBLE,
        proto.RELOCATION_TYPE_RELOCATION_DESIRABLE: hh.RelocationTypeEnum.RELOCATION_DESIRABLE,
    }

    @classmethod
    def to_proto(cls, value: hh.RelocationTypeEnum) -> proto.RelocationType.ValueType:
        return cls.RELOCATION_TYPE_PROTO.get(value, proto.RELOCATION_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.RelocationType.ValueType) -> hh.RelocationTypeEnum | None:
        return cls.RELOCATION_TYPE_PYTHON.get(value, None)


@final
class BusinessTripReadinessMapper:
    BUSINESS_TRIP_READINESS_PROTO: ClassVar[
        dict[hh.BusinessTripReadinessEnum, proto.BusinessTripReadiness.ValueType]
    ] = {
        hh.BusinessTripReadinessEnum.READY: proto.BUSINESS_TRIP_READINESS_READY,
        hh.BusinessTripReadinessEnum.SOMETIMES: proto.BUSINESS_TRIP_READINESS_SOMETIMES,
        hh.BusinessTripReadinessEnum.NEVER: proto.BUSINESS_TRIP_READINESS_NEVER,
    }
    BUSINESS_TRIP_READINESS_PYTHON: ClassVar[
        dict[proto.BusinessTripReadiness.ValueType, hh.BusinessTripReadinessEnum]
    ] = {
        proto.BUSINESS_TRIP_READINESS_READY: hh.BusinessTripReadinessEnum.READY,
        proto.BUSINESS_TRIP_READINESS_SOMETIMES: hh.BusinessTripReadinessEnum.SOMETIMES,
        proto.BUSINESS_TRIP_READINESS_NEVER: hh.BusinessTripReadinessEnum.NEVER,
    }

    @classmethod
    def to_proto(cls, value: hh.BusinessTripReadinessEnum) -> proto.BusinessTripReadiness.ValueType:
        return cls.BUSINESS_TRIP_READINESS_PROTO.get(value, proto.BUSINESS_TRIP_READINESS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.BusinessTripReadiness.ValueType) -> hh.BusinessTripReadinessEnum | None:
        return cls.BUSINESS_TRIP_READINESS_PYTHON.get(value, None)


@final
class ResumeContactsSiteTypeMapper:
    RESUME_CONTACTS_SITE_TYPE_PROTO: ClassVar[
        dict[hh.ResumeContactsSiteTypeEnum, proto.ResumeContactsSiteType.ValueType]
    ] = {
        hh.ResumeContactsSiteTypeEnum.PERSONAL: proto.RESUME_CONTACTS_SITE_TYPE_PERSONAL,
        hh.ResumeContactsSiteTypeEnum.MOI_KRUG: proto.RESUME_CONTACTS_SITE_TYPE_MOI_KRUG,
        hh.ResumeContactsSiteTypeEnum.LIVEJOURNAL: proto.RESUME_CONTACTS_SITE_TYPE_LIVEJOURNAL,
        hh.ResumeContactsSiteTypeEnum.LINKEDIN: proto.RESUME_CONTACTS_SITE_TYPE_LINKEDIN,
        hh.ResumeContactsSiteTypeEnum.FREELANCE: proto.RESUME_CONTACTS_SITE_TYPE_FREELANCE,
        hh.ResumeContactsSiteTypeEnum.SKYPE: proto.RESUME_CONTACTS_SITE_TYPE_SKYPE,
    }
    RESUME_CONTACTS_SITE_TYPE_PYTHON: ClassVar[
        dict[proto.ResumeContactsSiteType.ValueType, hh.ResumeContactsSiteTypeEnum]
    ] = {
        proto.RESUME_CONTACTS_SITE_TYPE_PERSONAL: hh.ResumeContactsSiteTypeEnum.PERSONAL,
        proto.RESUME_CONTACTS_SITE_TYPE_MOI_KRUG: hh.ResumeContactsSiteTypeEnum.MOI_KRUG,
        proto.RESUME_CONTACTS_SITE_TYPE_LIVEJOURNAL: hh.ResumeContactsSiteTypeEnum.LIVEJOURNAL,
        proto.RESUME_CONTACTS_SITE_TYPE_LINKEDIN: hh.ResumeContactsSiteTypeEnum.LINKEDIN,
        proto.RESUME_CONTACTS_SITE_TYPE_FREELANCE: hh.ResumeContactsSiteTypeEnum.FREELANCE,
        proto.RESUME_CONTACTS_SITE_TYPE_SKYPE: hh.ResumeContactsSiteTypeEnum.SKYPE,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeContactsSiteTypeEnum) -> proto.ResumeContactsSiteType.ValueType:
        return cls.RESUME_CONTACTS_SITE_TYPE_PROTO.get(value, proto.RESUME_CONTACTS_SITE_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeContactsSiteType.ValueType) -> hh.ResumeContactsSiteTypeEnum | None:
        return cls.RESUME_CONTACTS_SITE_TYPE_PYTHON.get(value, None)


@final
class EmployerTypeMapper:
    EMPLOYER_TYPE_PROTO: ClassVar[dict[hh.EmployerTypeEnum, proto.EmployerType.ValueType]] = {
        hh.EmployerTypeEnum.COMPANY: proto.EMPLOYER_TYPE_COMPANY,
        hh.EmployerTypeEnum.AGENCY: proto.EMPLOYER_TYPE_AGENCY,
        hh.EmployerTypeEnum.PROJECT_DIRECTOR: proto.EMPLOYER_TYPE_PROJECT_DIRECTOR,
        hh.EmployerTypeEnum.PRIVATE_RECRUITER: proto.EMPLOYER_TYPE_PRIVATE_RECRUITER,
        hh.EmployerTypeEnum.PRIVATE_INDIVIDUAL: proto.EMPLOYER_TYPE_PRIVATE_INDIVIDUAL,
        hh.EmployerTypeEnum.SELF_EMPLOYED: proto.EMPLOYER_TYPE_SELF_EMPLOYED,
    }
    EMPLOYER_TYPE_PYTHON: ClassVar[dict[proto.EmployerType.ValueType, hh.EmployerTypeEnum]] = {
        proto.EMPLOYER_TYPE_COMPANY: hh.EmployerTypeEnum.COMPANY,
        proto.EMPLOYER_TYPE_AGENCY: hh.EmployerTypeEnum.AGENCY,
        proto.EMPLOYER_TYPE_PROJECT_DIRECTOR: hh.EmployerTypeEnum.PROJECT_DIRECTOR,
        proto.EMPLOYER_TYPE_PRIVATE_RECRUITER: hh.EmployerTypeEnum.PRIVATE_RECRUITER,
        proto.EMPLOYER_TYPE_PRIVATE_INDIVIDUAL: hh.EmployerTypeEnum.PRIVATE_INDIVIDUAL,
        proto.EMPLOYER_TYPE_SELF_EMPLOYED: hh.EmployerTypeEnum.SELF_EMPLOYED,
    }

    @classmethod
    def to_proto(cls, value: hh.EmployerTypeEnum) -> proto.EmployerType.ValueType:
        return cls.EMPLOYER_TYPE_PROTO.get(value, proto.EMPLOYER_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.EmployerType.ValueType) -> hh.EmployerTypeEnum | None:
        return cls.EMPLOYER_TYPE_PYTHON.get(value, None)


@final
class EmployerRelationMapper:
    EMPLOYER_RELATION_PROTO: ClassVar[dict[hh.EmployerRelationEnum, proto.EmployerRelation.ValueType]] = {
        hh.EmployerRelationEnum.BLACKLISTED: proto.EMPLOYER_RELATION_BLACKLISTED,
    }
    EMPLOYER_RELATION_PYTHON: ClassVar[dict[proto.EmployerRelation.ValueType, hh.EmployerRelationEnum]] = {
        proto.EMPLOYER_RELATION_BLACKLISTED: hh.EmployerRelationEnum.BLACKLISTED,
    }

    @classmethod
    def to_proto(cls, value: hh.EmployerRelationEnum) -> proto.EmployerRelation.ValueType:
        return cls.EMPLOYER_RELATION_PROTO.get(value, proto.EMPLOYER_RELATION_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.EmployerRelation.ValueType) -> hh.EmployerRelationEnum | None:
        return cls.EMPLOYER_RELATION_PYTHON.get(value, None)


@final
class NegotiationsStateMapper:
    NEGOTIATIONS_STATE_PROTO: ClassVar[dict[hh.NegotiationsStateEnum, proto.NegotiationsState.ValueType]] = {
        hh.NegotiationsStateEnum.RESPONSE: proto.NEGOTIATIONS_STATE_RESPONSE,
        hh.NegotiationsStateEnum.INVITATION: proto.NEGOTIATIONS_STATE_INVITATION,
        hh.NegotiationsStateEnum.DISCARD: proto.NEGOTIATIONS_STATE_DISCARD,
        hh.NegotiationsStateEnum.HIDDEN: proto.NEGOTIATIONS_STATE_HIDDEN,
        hh.NegotiationsStateEnum.INTERVIEW: proto.NEGOTIATIONS_STATE_INTERVIEW,
        hh.NegotiationsStateEnum.HIRED: proto.NEGOTIATIONS_STATE_HIRED,
    }
    NEGOTIATIONS_STATE_PYTHON: ClassVar[dict[proto.NegotiationsState.ValueType, hh.NegotiationsStateEnum]] = {
        proto.NEGOTIATIONS_STATE_RESPONSE: hh.NegotiationsStateEnum.RESPONSE,
        proto.NEGOTIATIONS_STATE_INVITATION: hh.NegotiationsStateEnum.INVITATION,
        proto.NEGOTIATIONS_STATE_DISCARD: hh.NegotiationsStateEnum.DISCARD,
        proto.NEGOTIATIONS_STATE_HIDDEN: hh.NegotiationsStateEnum.HIDDEN,
        proto.NEGOTIATIONS_STATE_INTERVIEW: hh.NegotiationsStateEnum.INTERVIEW,
        proto.NEGOTIATIONS_STATE_HIRED: hh.NegotiationsStateEnum.HIRED,
    }

    @classmethod
    def to_proto(cls, value: hh.NegotiationsStateEnum) -> proto.NegotiationsState.ValueType:
        return cls.NEGOTIATIONS_STATE_PROTO.get(value, proto.NEGOTIATIONS_STATE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.NegotiationsState.ValueType) -> hh.NegotiationsStateEnum | None:
        return cls.NEGOTIATIONS_STATE_PYTHON.get(value, None)


@final
class ApplicantNegotiationStatusMapper:
    APPLICANT_NEGOTIATION_STATUS_PROTO: ClassVar[
        dict[hh.ApplicantNegotiationStatusEnum, proto.ApplicantNegotiationStatus.ValueType]
    ] = {
        hh.ApplicantNegotiationStatusEnum.ALL: proto.APPLICANT_NEGOTIATION_STATUS_ALL,
        hh.ApplicantNegotiationStatusEnum.ACTIVE: proto.APPLICANT_NEGOTIATION_STATUS_ACTIVE,
        hh.ApplicantNegotiationStatusEnum.INVITATIONS: proto.APPLICANT_NEGOTIATION_STATUS_INVITATIONS,
        hh.ApplicantNegotiationStatusEnum.RESPONSE: proto.APPLICANT_NEGOTIATION_STATUS_RESPONSE,
        hh.ApplicantNegotiationStatusEnum.DISCARD: proto.APPLICANT_NEGOTIATION_STATUS_DISCARD,
        hh.ApplicantNegotiationStatusEnum.ARCHIVED: proto.APPLICANT_NEGOTIATION_STATUS_ARCHIVED,
        hh.ApplicantNegotiationStatusEnum.NON_ARCHIVED: proto.APPLICANT_NEGOTIATION_STATUS_NON_ARCHIVED,
        hh.ApplicantNegotiationStatusEnum.DELETED: proto.APPLICANT_NEGOTIATION_STATUS_DELETED,
        hh.ApplicantNegotiationStatusEnum.INTERVIEW: proto.APPLICANT_NEGOTIATION_STATUS_INTERVIEW,
        hh.ApplicantNegotiationStatusEnum.HIRED: proto.APPLICANT_NEGOTIATION_STATUS_HIRED,
    }
    APPLICANT_NEGOTIATION_STATUS_PYTHON: ClassVar[
        dict[proto.ApplicantNegotiationStatus.ValueType, hh.ApplicantNegotiationStatusEnum]
    ] = {
        proto.APPLICANT_NEGOTIATION_STATUS_ALL: hh.ApplicantNegotiationStatusEnum.ALL,
        proto.APPLICANT_NEGOTIATION_STATUS_ACTIVE: hh.ApplicantNegotiationStatusEnum.ACTIVE,
        proto.APPLICANT_NEGOTIATION_STATUS_INVITATIONS: hh.ApplicantNegotiationStatusEnum.INVITATIONS,
        proto.APPLICANT_NEGOTIATION_STATUS_RESPONSE: hh.ApplicantNegotiationStatusEnum.RESPONSE,
        proto.APPLICANT_NEGOTIATION_STATUS_DISCARD: hh.ApplicantNegotiationStatusEnum.DISCARD,
        proto.APPLICANT_NEGOTIATION_STATUS_ARCHIVED: hh.ApplicantNegotiationStatusEnum.ARCHIVED,
        proto.APPLICANT_NEGOTIATION_STATUS_NON_ARCHIVED: hh.ApplicantNegotiationStatusEnum.NON_ARCHIVED,
        proto.APPLICANT_NEGOTIATION_STATUS_DELETED: hh.ApplicantNegotiationStatusEnum.DELETED,
        proto.APPLICANT_NEGOTIATION_STATUS_INTERVIEW: hh.ApplicantNegotiationStatusEnum.INTERVIEW,
        proto.APPLICANT_NEGOTIATION_STATUS_HIRED: hh.ApplicantNegotiationStatusEnum.HIRED,
    }

    @classmethod
    def to_proto(cls, value: hh.ApplicantNegotiationStatusEnum) -> proto.ApplicantNegotiationStatus.ValueType:
        return cls.APPLICANT_NEGOTIATION_STATUS_PROTO.get(value, proto.APPLICANT_NEGOTIATION_STATUS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ApplicantNegotiationStatus.ValueType) -> hh.ApplicantNegotiationStatusEnum | None:
        return cls.APPLICANT_NEGOTIATION_STATUS_PYTHON.get(value, None)


@final
class NegotiationsParticipantTypeMapper:
    NEGOTIATIONS_PARTICIPANT_TYPE_PROTO: ClassVar[
        dict[hh.NegotiationsParticipantTypeEnum, proto.NegotiationsParticipantType.ValueType]
    ] = {
        hh.NegotiationsParticipantTypeEnum.APPLICANT: proto.NEGOTIATIONS_PARTICIPANT_TYPE_APPLICANT,
        hh.NegotiationsParticipantTypeEnum.EMPLOYER: proto.NEGOTIATIONS_PARTICIPANT_TYPE_EMPLOYER,
    }
    NEGOTIATIONS_PARTICIPANT_TYPE_PYTHON: ClassVar[
        dict[proto.NegotiationsParticipantType.ValueType, hh.NegotiationsParticipantTypeEnum]
    ] = {
        proto.NEGOTIATIONS_PARTICIPANT_TYPE_APPLICANT: hh.NegotiationsParticipantTypeEnum.APPLICANT,
        proto.NEGOTIATIONS_PARTICIPANT_TYPE_EMPLOYER: hh.NegotiationsParticipantTypeEnum.EMPLOYER,
    }

    @classmethod
    def to_proto(cls, value: hh.NegotiationsParticipantTypeEnum) -> proto.NegotiationsParticipantType.ValueType:
        return cls.NEGOTIATIONS_PARTICIPANT_TYPE_PROTO.get(value, proto.NEGOTIATIONS_PARTICIPANT_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.NegotiationsParticipantType.ValueType) -> hh.NegotiationsParticipantTypeEnum | None:
        return cls.NEGOTIATIONS_PARTICIPANT_TYPE_PYTHON.get(value, None)


@final
class NegotiationsOrderMapper:
    NEGOTIATIONS_ORDER_PROTO: ClassVar[dict[hh.NegotiationsOrderEnum, proto.NegotiationsOrder.ValueType]] = {
        hh.NegotiationsOrderEnum.UPDATED_AT: proto.NEGOTIATIONS_ORDER_UPDATED_AT,
        hh.NegotiationsOrderEnum.CREATED_AT: proto.NEGOTIATIONS_ORDER_CREATED_AT,
    }
    NEGOTIATIONS_ORDER_PYTHON: ClassVar[dict[proto.NegotiationsOrder.ValueType, hh.NegotiationsOrderEnum]] = {
        proto.NEGOTIATIONS_ORDER_UPDATED_AT: hh.NegotiationsOrderEnum.UPDATED_AT,
        proto.NEGOTIATIONS_ORDER_CREATED_AT: hh.NegotiationsOrderEnum.CREATED_AT,
    }

    @classmethod
    def to_proto(cls, value: hh.NegotiationsOrderEnum) -> proto.NegotiationsOrder.ValueType:
        return cls.NEGOTIATIONS_ORDER_PROTO.get(value, proto.NEGOTIATIONS_ORDER_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.NegotiationsOrder.ValueType) -> hh.NegotiationsOrderEnum | None:
        return cls.NEGOTIATIONS_ORDER_PYTHON.get(value, None)


@final
class ResumeModerationNoteMapper:
    RESUME_MODERATION_NOTE_PROTO: ClassVar[dict[hh.ResumeModerationNoteEnum, proto.ResumeModerationNote.ValueType]] = {
        hh.ResumeModerationNoteEnum.BAD: proto.RESUME_MODERATION_NOTE_BAD,
        hh.ResumeModerationNoteEnum.BLOCK_FULL_NAME: proto.RESUME_MODERATION_NOTE_BLOCK_FULL_NAME,
        hh.ResumeModerationNoteEnum.BAD_DESCRIPTION: proto.RESUME_MODERATION_NOTE_BAD_DESCRIPTION,
        hh.ResumeModerationNoteEnum.BLOCK_NO_EDUCATION_PLACE_OR_DATE: proto.RESUME_MODERATION_NOTE_BLOCK_NO_EDUCATION_PLACE_OR_DATE,
        hh.ResumeModerationNoteEnum.BAD_EDUCATION: proto.RESUME_MODERATION_NOTE_BAD_EDUCATION,
        hh.ResumeModerationNoteEnum.BAD_EDUCATION_STUDENT: proto.RESUME_MODERATION_NOTE_BAD_EDUCATION_STUDENT,
        hh.ResumeModerationNoteEnum.BLOCK_NO_FUNCTION: proto.RESUME_MODERATION_NOTE_BLOCK_NO_FUNCTION,
        hh.ResumeModerationNoteEnum.BLOCK_WORK_PLACE: proto.RESUME_MODERATION_NOTE_BLOCK_WORK_PLACE,
        hh.ResumeModerationNoteEnum.NO_COMPANY_NAME: proto.RESUME_MODERATION_NOTE_NO_COMPANY_NAME,
        hh.ResumeModerationNoteEnum.NO_COMPANY_DESCRIPTION: proto.RESUME_MODERATION_NOTE_NO_COMPANY_DESCRIPTION,
        hh.ResumeModerationNoteEnum.NO_POSITION: proto.RESUME_MODERATION_NOTE_NO_POSITION,
        hh.ResumeModerationNoteEnum.NO_DATE: proto.RESUME_MODERATION_NOTE_NO_DATE,
        hh.ResumeModerationNoteEnum.BAD_FUNCTION: proto.RESUME_MODERATION_NOTE_BAD_FUNCTION,
        hh.ResumeModerationNoteEnum.NOT_ENOUGH_INFORMATION: proto.RESUME_MODERATION_NOTE_NOT_ENOUGH_INFORMATION,
        hh.ResumeModerationNoteEnum.LOT_INFORMATION: proto.RESUME_MODERATION_NOTE_LOT_INFORMATION,
        hh.ResumeModerationNoteEnum.NO_RECOMMENDATION: proto.RESUME_MODERATION_NOTE_NO_RECOMMENDATION,
        hh.ResumeModerationNoteEnum.CARELESS_ADDITIONAL_INFORMATION: proto.RESUME_MODERATION_NOTE_CARELESS_ADDITIONAL_INFORMATION,
        hh.ResumeModerationNoteEnum.CARELESS_PHOTO: proto.RESUME_MODERATION_NOTE_CARELESS_PHOTO,
        hh.ResumeModerationNoteEnum.CARELESS_KEY_SKILL_INFORMATION: proto.RESUME_MODERATION_NOTE_CARELESS_KEY_SKILL_INFORMATION,
        hh.ResumeModerationNoteEnum.INCORRECT_PHONE_NUMBER: proto.RESUME_MODERATION_NOTE_INCORRECT_PHONE_NUMBER,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_NAME: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_NAME,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_TITLE: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_TITLE,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_EXPERIENCE: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_EXPERIENCE,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_SKILLS: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_SKILLS,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_KEY_SKILLS: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_KEY_SKILLS,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_EDUCATION: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_EDUCATION,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_ADDITIONAL_EDUCATION: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_ADDITIONAL_EDUCATION,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_ATTESTATION_EDUCATION: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_ATTESTATION_EDUCATION,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_ELEMENTARY_EDUCATION: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_ELEMENTARY_EDUCATION,
        hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_RECOMMENDATION: proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_RECOMMENDATION,
        hh.ResumeModerationNoteEnum.BLOCK_EXPERIENCE_IN_ONE_PLACE: proto.RESUME_MODERATION_NOTE_BLOCK_EXPERIENCE_IN_ONE_PLACE,
        hh.ResumeModerationNoteEnum.EXPERIENCE_CAPS: proto.RESUME_MODERATION_NOTE_EXPERIENCE_CAPS,
        hh.ResumeModerationNoteEnum.EXPERIENCE_MULTILANG: proto.RESUME_MODERATION_NOTE_EXPERIENCE_MULTILANG,
        hh.ResumeModerationNoteEnum.EXPERIENCE_SPELLING: proto.RESUME_MODERATION_NOTE_EXPERIENCE_SPELLING,
        hh.ResumeModerationNoteEnum.BLOCK_EXPERIENCE_IN_ADDITIONAL_INFORMATION: proto.RESUME_MODERATION_NOTE_BLOCK_EXPERIENCE_IN_ADDITIONAL_INFORMATION,
        hh.ResumeModerationNoteEnum.ADDITIONAL_INFORMATION_CAPS: proto.RESUME_MODERATION_NOTE_ADDITIONAL_INFORMATION_CAPS,
        hh.ResumeModerationNoteEnum.ADDITIONAL_INFORMATION_MULTILANG: proto.RESUME_MODERATION_NOTE_ADDITIONAL_INFORMATION_MULTILANG,
        hh.ResumeModerationNoteEnum.ADDITIONAL_INFORMATION_SPELLING: proto.RESUME_MODERATION_NOTE_ADDITIONAL_INFORMATION_SPELLING,
    }
    RESUME_MODERATION_NOTE_PYTHON: ClassVar[dict[proto.ResumeModerationNote.ValueType, hh.ResumeModerationNoteEnum]] = {
        proto.RESUME_MODERATION_NOTE_BAD: hh.ResumeModerationNoteEnum.BAD,
        proto.RESUME_MODERATION_NOTE_BLOCK_FULL_NAME: hh.ResumeModerationNoteEnum.BLOCK_FULL_NAME,
        proto.RESUME_MODERATION_NOTE_BAD_DESCRIPTION: hh.ResumeModerationNoteEnum.BAD_DESCRIPTION,
        proto.RESUME_MODERATION_NOTE_BLOCK_NO_EDUCATION_PLACE_OR_DATE: hh.ResumeModerationNoteEnum.BLOCK_NO_EDUCATION_PLACE_OR_DATE,
        proto.RESUME_MODERATION_NOTE_BAD_EDUCATION: hh.ResumeModerationNoteEnum.BAD_EDUCATION,
        proto.RESUME_MODERATION_NOTE_BAD_EDUCATION_STUDENT: hh.ResumeModerationNoteEnum.BAD_EDUCATION_STUDENT,
        proto.RESUME_MODERATION_NOTE_BLOCK_NO_FUNCTION: hh.ResumeModerationNoteEnum.BLOCK_NO_FUNCTION,
        proto.RESUME_MODERATION_NOTE_BLOCK_WORK_PLACE: hh.ResumeModerationNoteEnum.BLOCK_WORK_PLACE,
        proto.RESUME_MODERATION_NOTE_NO_COMPANY_NAME: hh.ResumeModerationNoteEnum.NO_COMPANY_NAME,
        proto.RESUME_MODERATION_NOTE_NO_COMPANY_DESCRIPTION: hh.ResumeModerationNoteEnum.NO_COMPANY_DESCRIPTION,
        proto.RESUME_MODERATION_NOTE_NO_POSITION: hh.ResumeModerationNoteEnum.NO_POSITION,
        proto.RESUME_MODERATION_NOTE_NO_DATE: hh.ResumeModerationNoteEnum.NO_DATE,
        proto.RESUME_MODERATION_NOTE_BAD_FUNCTION: hh.ResumeModerationNoteEnum.BAD_FUNCTION,
        proto.RESUME_MODERATION_NOTE_NOT_ENOUGH_INFORMATION: hh.ResumeModerationNoteEnum.NOT_ENOUGH_INFORMATION,
        proto.RESUME_MODERATION_NOTE_LOT_INFORMATION: hh.ResumeModerationNoteEnum.LOT_INFORMATION,
        proto.RESUME_MODERATION_NOTE_NO_RECOMMENDATION: hh.ResumeModerationNoteEnum.NO_RECOMMENDATION,
        proto.RESUME_MODERATION_NOTE_CARELESS_ADDITIONAL_INFORMATION: hh.ResumeModerationNoteEnum.CARELESS_ADDITIONAL_INFORMATION,
        proto.RESUME_MODERATION_NOTE_CARELESS_PHOTO: hh.ResumeModerationNoteEnum.CARELESS_PHOTO,
        proto.RESUME_MODERATION_NOTE_CARELESS_KEY_SKILL_INFORMATION: hh.ResumeModerationNoteEnum.CARELESS_KEY_SKILL_INFORMATION,
        proto.RESUME_MODERATION_NOTE_INCORRECT_PHONE_NUMBER: hh.ResumeModerationNoteEnum.INCORRECT_PHONE_NUMBER,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_NAME: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_NAME,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_TITLE: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_TITLE,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_EXPERIENCE: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_EXPERIENCE,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_SKILLS: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_SKILLS,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_KEY_SKILLS: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_KEY_SKILLS,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_EDUCATION: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_EDUCATION,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_ADDITIONAL_EDUCATION: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_ADDITIONAL_EDUCATION,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_ATTESTATION_EDUCATION: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_ATTESTATION_EDUCATION,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_ELEMENTARY_EDUCATION: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_ELEMENTARY_EDUCATION,
        proto.RESUME_MODERATION_NOTE_BLOCK_OBSCENITY_RECOMMENDATION: hh.ResumeModerationNoteEnum.BLOCK_OBSCENITY_RECOMMENDATION,
        proto.RESUME_MODERATION_NOTE_BLOCK_EXPERIENCE_IN_ONE_PLACE: hh.ResumeModerationNoteEnum.BLOCK_EXPERIENCE_IN_ONE_PLACE,
        proto.RESUME_MODERATION_NOTE_EXPERIENCE_CAPS: hh.ResumeModerationNoteEnum.EXPERIENCE_CAPS,
        proto.RESUME_MODERATION_NOTE_EXPERIENCE_MULTILANG: hh.ResumeModerationNoteEnum.EXPERIENCE_MULTILANG,
        proto.RESUME_MODERATION_NOTE_EXPERIENCE_SPELLING: hh.ResumeModerationNoteEnum.EXPERIENCE_SPELLING,
        proto.RESUME_MODERATION_NOTE_BLOCK_EXPERIENCE_IN_ADDITIONAL_INFORMATION: hh.ResumeModerationNoteEnum.BLOCK_EXPERIENCE_IN_ADDITIONAL_INFORMATION,
        proto.RESUME_MODERATION_NOTE_ADDITIONAL_INFORMATION_CAPS: hh.ResumeModerationNoteEnum.ADDITIONAL_INFORMATION_CAPS,
        proto.RESUME_MODERATION_NOTE_ADDITIONAL_INFORMATION_MULTILANG: hh.ResumeModerationNoteEnum.ADDITIONAL_INFORMATION_MULTILANG,
        proto.RESUME_MODERATION_NOTE_ADDITIONAL_INFORMATION_SPELLING: hh.ResumeModerationNoteEnum.ADDITIONAL_INFORMATION_SPELLING,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeModerationNoteEnum) -> proto.ResumeModerationNote.ValueType:
        return cls.RESUME_MODERATION_NOTE_PROTO.get(value, proto.RESUME_MODERATION_NOTE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeModerationNote.ValueType) -> hh.ResumeModerationNoteEnum | None:
        return cls.RESUME_MODERATION_NOTE_PYTHON.get(value, None)


@final
class VacancyRelationMapper:
    VACANCY_RELATION_PROTO: ClassVar[dict[hh.VacancyRelationEnum, proto.VacancyRelation.ValueType]] = {
        hh.VacancyRelationEnum.FAVORITED: proto.VACANCY_RELATION_FAVORITED,
        hh.VacancyRelationEnum.GOT_RESPONSE: proto.VACANCY_RELATION_GOT_RESPONSE,
        hh.VacancyRelationEnum.GOT_INVITATION: proto.VACANCY_RELATION_GOT_INVITATION,
        hh.VacancyRelationEnum.GOT_REJECTION: proto.VACANCY_RELATION_GOT_REJECTION,
        hh.VacancyRelationEnum.BLACKLISTED: proto.VACANCY_RELATION_BLACKLISTED,
        hh.VacancyRelationEnum.GOT_QUESTION: proto.VACANCY_RELATION_GOT_QUESTION,
    }
    VACANCY_RELATION_PYTHON: ClassVar[dict[proto.VacancyRelation.ValueType, hh.VacancyRelationEnum]] = {
        proto.VACANCY_RELATION_FAVORITED: hh.VacancyRelationEnum.FAVORITED,
        proto.VACANCY_RELATION_GOT_RESPONSE: hh.VacancyRelationEnum.GOT_RESPONSE,
        proto.VACANCY_RELATION_GOT_INVITATION: hh.VacancyRelationEnum.GOT_INVITATION,
        proto.VACANCY_RELATION_GOT_REJECTION: hh.VacancyRelationEnum.GOT_REJECTION,
        proto.VACANCY_RELATION_BLACKLISTED: hh.VacancyRelationEnum.BLACKLISTED,
        proto.VACANCY_RELATION_GOT_QUESTION: hh.VacancyRelationEnum.GOT_QUESTION,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancyRelationEnum) -> proto.VacancyRelation.ValueType:
        return cls.VACANCY_RELATION_PROTO.get(value, proto.VACANCY_RELATION_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancyRelation.ValueType) -> hh.VacancyRelationEnum | None:
        return cls.VACANCY_RELATION_PYTHON.get(value, None)


@final
class ResumeStatusMapper:
    RESUME_STATUS_PROTO: ClassVar[dict[hh.ResumeStatusEnum, proto.ResumeStatus.ValueType]] = {
        hh.ResumeStatusEnum.NOT_PUBLISHED: proto.RESUME_STATUS_NOT_PUBLISHED,
        hh.ResumeStatusEnum.PUBLISHED: proto.RESUME_STATUS_PUBLISHED,
        hh.ResumeStatusEnum.BLOCKED: proto.RESUME_STATUS_BLOCKED,
        hh.ResumeStatusEnum.ON_MODERATION: proto.RESUME_STATUS_ON_MODERATION,
    }
    RESUME_STATUS_PYTHON: ClassVar[dict[proto.ResumeStatus.ValueType, hh.ResumeStatusEnum]] = {
        proto.RESUME_STATUS_NOT_PUBLISHED: hh.ResumeStatusEnum.NOT_PUBLISHED,
        proto.RESUME_STATUS_PUBLISHED: hh.ResumeStatusEnum.PUBLISHED,
        proto.RESUME_STATUS_BLOCKED: hh.ResumeStatusEnum.BLOCKED,
        proto.RESUME_STATUS_ON_MODERATION: hh.ResumeStatusEnum.ON_MODERATION,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeStatusEnum) -> proto.ResumeStatus.ValueType:
        return cls.RESUME_STATUS_PROTO.get(value, proto.RESUME_STATUS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeStatus.ValueType) -> hh.ResumeStatusEnum | None:
        return cls.RESUME_STATUS_PYTHON.get(value, None)


@final
class ResumeSearchLogicMapper:
    RESUME_SEARCH_LOGIC_PROTO: ClassVar[dict[hh.ResumeSearchLogicEnum, proto.ResumeSearchLogic.ValueType]] = {
        hh.ResumeSearchLogicEnum.ALL: proto.RESUME_SEARCH_LOGIC_ALL,
        hh.ResumeSearchLogicEnum.ANY: proto.RESUME_SEARCH_LOGIC_ANY,
        hh.ResumeSearchLogicEnum.PHRASE: proto.RESUME_SEARCH_LOGIC_PHRASE,
        hh.ResumeSearchLogicEnum.EXCEPT: proto.RESUME_SEARCH_LOGIC_EXCEPT,
    }
    RESUME_SEARCH_LOGIC_PYTHON: ClassVar[dict[proto.ResumeSearchLogic.ValueType, hh.ResumeSearchLogicEnum]] = {
        proto.RESUME_SEARCH_LOGIC_ALL: hh.ResumeSearchLogicEnum.ALL,
        proto.RESUME_SEARCH_LOGIC_ANY: hh.ResumeSearchLogicEnum.ANY,
        proto.RESUME_SEARCH_LOGIC_PHRASE: hh.ResumeSearchLogicEnum.PHRASE,
        proto.RESUME_SEARCH_LOGIC_EXCEPT: hh.ResumeSearchLogicEnum.EXCEPT,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeSearchLogicEnum) -> proto.ResumeSearchLogic.ValueType:
        return cls.RESUME_SEARCH_LOGIC_PROTO.get(value, proto.RESUME_SEARCH_LOGIC_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeSearchLogic.ValueType) -> hh.ResumeSearchLogicEnum | None:
        return cls.RESUME_SEARCH_LOGIC_PYTHON.get(value, None)


@final
class ResumeSearchFieldsMapper:
    RESUME_SEARCH_FIELDS_PROTO: ClassVar[dict[hh.ResumeSearchFieldsEnum, proto.ResumeSearchFields.ValueType]] = {
        hh.ResumeSearchFieldsEnum.EVERYWHERE: proto.RESUME_SEARCH_FIELDS_EVERYWHERE,
        hh.ResumeSearchFieldsEnum.TITLE: proto.RESUME_SEARCH_FIELDS_TITLE,
        hh.ResumeSearchFieldsEnum.EDUCATION: proto.RESUME_SEARCH_FIELDS_EDUCATION,
        hh.ResumeSearchFieldsEnum.SKILLS: proto.RESUME_SEARCH_FIELDS_SKILLS,
        hh.ResumeSearchFieldsEnum.EXPERIENCE: proto.RESUME_SEARCH_FIELDS_EXPERIENCE,
        hh.ResumeSearchFieldsEnum.EXPERIENCE_COMPANY: proto.RESUME_SEARCH_FIELDS_EXPERIENCE_COMPANY,
        hh.ResumeSearchFieldsEnum.EXPERIENCE_POSITION: proto.RESUME_SEARCH_FIELDS_EXPERIENCE_POSITION,
        hh.ResumeSearchFieldsEnum.EXPERIENCE_DESCRIPTION: proto.RESUME_SEARCH_FIELDS_EXPERIENCE_DESCRIPTION,
    }
    RESUME_SEARCH_FIELDS_PYTHON: ClassVar[dict[proto.ResumeSearchFields.ValueType, hh.ResumeSearchFieldsEnum]] = {
        proto.RESUME_SEARCH_FIELDS_EVERYWHERE: hh.ResumeSearchFieldsEnum.EVERYWHERE,
        proto.RESUME_SEARCH_FIELDS_TITLE: hh.ResumeSearchFieldsEnum.TITLE,
        proto.RESUME_SEARCH_FIELDS_EDUCATION: hh.ResumeSearchFieldsEnum.EDUCATION,
        proto.RESUME_SEARCH_FIELDS_SKILLS: hh.ResumeSearchFieldsEnum.SKILLS,
        proto.RESUME_SEARCH_FIELDS_EXPERIENCE: hh.ResumeSearchFieldsEnum.EXPERIENCE,
        proto.RESUME_SEARCH_FIELDS_EXPERIENCE_COMPANY: hh.ResumeSearchFieldsEnum.EXPERIENCE_COMPANY,
        proto.RESUME_SEARCH_FIELDS_EXPERIENCE_POSITION: hh.ResumeSearchFieldsEnum.EXPERIENCE_POSITION,
        proto.RESUME_SEARCH_FIELDS_EXPERIENCE_DESCRIPTION: hh.ResumeSearchFieldsEnum.EXPERIENCE_DESCRIPTION,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeSearchFieldsEnum) -> proto.ResumeSearchFields.ValueType:
        return cls.RESUME_SEARCH_FIELDS_PROTO.get(value, proto.RESUME_SEARCH_FIELDS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeSearchFields.ValueType) -> hh.ResumeSearchFieldsEnum | None:
        return cls.RESUME_SEARCH_FIELDS_PYTHON.get(value, None)


@final
class MessagingStatusMapper:
    MESSAGING_STATUS_PROTO: ClassVar[dict[hh.MessagingStatusEnum, proto.MessagingStatus.ValueType]] = {
        hh.MessagingStatusEnum.ARCHIVED: proto.MESSAGING_STATUS_ARCHIVED,
        hh.MessagingStatusEnum.OK: proto.MESSAGING_STATUS_OK,
        hh.MessagingStatusEnum.DISABLED_BY_EMPLOYER: proto.MESSAGING_STATUS_DISABLED_BY_EMPLOYER,
        hh.MessagingStatusEnum.IN_A_ROW_LIMIT: proto.MESSAGING_STATUS_IN_A_ROW_LIMIT,
        hh.MessagingStatusEnum.OVERALL_LIMIT: proto.MESSAGING_STATUS_OVERALL_LIMIT,
        hh.MessagingStatusEnum.NO_INVITATION: proto.MESSAGING_STATUS_NO_INVITATION,
        hh.MessagingStatusEnum.RESUME_DELETED: proto.MESSAGING_STATUS_RESUME_DELETED,
        hh.MessagingStatusEnum.PROHIBITED: proto.MESSAGING_STATUS_PROHIBITED,
    }
    MESSAGING_STATUS_PYTHON: ClassVar[dict[proto.MessagingStatus.ValueType, hh.MessagingStatusEnum]] = {
        proto.MESSAGING_STATUS_ARCHIVED: hh.MessagingStatusEnum.ARCHIVED,
        proto.MESSAGING_STATUS_OK: hh.MessagingStatusEnum.OK,
        proto.MESSAGING_STATUS_DISABLED_BY_EMPLOYER: hh.MessagingStatusEnum.DISABLED_BY_EMPLOYER,
        proto.MESSAGING_STATUS_IN_A_ROW_LIMIT: hh.MessagingStatusEnum.IN_A_ROW_LIMIT,
        proto.MESSAGING_STATUS_OVERALL_LIMIT: hh.MessagingStatusEnum.OVERALL_LIMIT,
        proto.MESSAGING_STATUS_NO_INVITATION: hh.MessagingStatusEnum.NO_INVITATION,
        proto.MESSAGING_STATUS_RESUME_DELETED: hh.MessagingStatusEnum.RESUME_DELETED,
        proto.MESSAGING_STATUS_PROHIBITED: hh.MessagingStatusEnum.PROHIBITED,
    }

    @classmethod
    def to_proto(cls, value: hh.MessagingStatusEnum) -> proto.MessagingStatus.ValueType:
        return cls.MESSAGING_STATUS_PROTO.get(value, proto.MESSAGING_STATUS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.MessagingStatus.ValueType) -> hh.MessagingStatusEnum | None:
        return cls.MESSAGING_STATUS_PYTHON.get(value, None)


@final
class EmployerActiveVacanciesOrderMapper:
    EMPLOYER_ACTIVE_VACANCIES_ORDER_PROTO: ClassVar[
        dict[hh.EmployerActiveVacanciesOrderEnum, proto.EmployerActiveVacanciesOrder.ValueType]
    ] = {
        hh.EmployerActiveVacanciesOrderEnum.NAME_ASC: proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_NAME_ASC,
        hh.EmployerActiveVacanciesOrderEnum.NAME_DESC: proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_NAME_DESC,
        hh.EmployerActiveVacanciesOrderEnum.EXPIRATION_DATE_ASC: proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_EXPIRATION_DATE_ASC,
        hh.EmployerActiveVacanciesOrderEnum.EXPIRATION_DATE_DESC: proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_EXPIRATION_DATE_DESC,
        hh.EmployerActiveVacanciesOrderEnum.UNSEEN_RESPONSES_ASC: proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_UNSEEN_RESPONSES_ASC,
        hh.EmployerActiveVacanciesOrderEnum.UNSEEN_RESPONSES_DESC: proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_UNSEEN_RESPONSES_DESC,
    }
    EMPLOYER_ACTIVE_VACANCIES_ORDER_PYTHON: ClassVar[
        dict[proto.EmployerActiveVacanciesOrder.ValueType, hh.EmployerActiveVacanciesOrderEnum]
    ] = {
        proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_NAME_ASC: hh.EmployerActiveVacanciesOrderEnum.NAME_ASC,
        proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_NAME_DESC: hh.EmployerActiveVacanciesOrderEnum.NAME_DESC,
        proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_EXPIRATION_DATE_ASC: hh.EmployerActiveVacanciesOrderEnum.EXPIRATION_DATE_ASC,
        proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_EXPIRATION_DATE_DESC: hh.EmployerActiveVacanciesOrderEnum.EXPIRATION_DATE_DESC,
        proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_UNSEEN_RESPONSES_ASC: hh.EmployerActiveVacanciesOrderEnum.UNSEEN_RESPONSES_ASC,
        proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_UNSEEN_RESPONSES_DESC: hh.EmployerActiveVacanciesOrderEnum.UNSEEN_RESPONSES_DESC,
    }

    @classmethod
    def to_proto(cls, value: hh.EmployerActiveVacanciesOrderEnum) -> proto.EmployerActiveVacanciesOrder.ValueType:
        return cls.EMPLOYER_ACTIVE_VACANCIES_ORDER_PROTO.get(value, proto.EMPLOYER_ACTIVE_VACANCIES_ORDER_UNSPECIFIED)

    @classmethod
    def to_python(
        cls, value: proto.EmployerActiveVacanciesOrder.ValueType
    ) -> hh.EmployerActiveVacanciesOrderEnum | None:
        return cls.EMPLOYER_ACTIVE_VACANCIES_ORDER_PYTHON.get(value, None)


@final
class EmployerArchivedVacanciesOrderMapper:
    EMPLOYER_ARCHIVED_VACANCIES_ORDER_PROTO: ClassVar[
        dict[hh.EmployerArchivedVacanciesOrderEnum, proto.EmployerArchivedVacanciesOrder.ValueType]
    ] = {
        hh.EmployerArchivedVacanciesOrderEnum.NAME_ASC: proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_NAME_ASC,
        hh.EmployerArchivedVacanciesOrderEnum.NAME_DESC: proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_NAME_DESC,
        hh.EmployerArchivedVacanciesOrderEnum.ARCHIVE_TIME_ASC: proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_ARCHIVE_TIME_ASC,
        hh.EmployerArchivedVacanciesOrderEnum.ARCHIVE_TIME_DESC: proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_ARCHIVE_TIME_DESC,
    }
    EMPLOYER_ARCHIVED_VACANCIES_ORDER_PYTHON: ClassVar[
        dict[proto.EmployerArchivedVacanciesOrder.ValueType, hh.EmployerArchivedVacanciesOrderEnum]
    ] = {
        proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_NAME_ASC: hh.EmployerArchivedVacanciesOrderEnum.NAME_ASC,
        proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_NAME_DESC: hh.EmployerArchivedVacanciesOrderEnum.NAME_DESC,
        proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_ARCHIVE_TIME_ASC: hh.EmployerArchivedVacanciesOrderEnum.ARCHIVE_TIME_ASC,
        proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_ARCHIVE_TIME_DESC: hh.EmployerArchivedVacanciesOrderEnum.ARCHIVE_TIME_DESC,
    }

    @classmethod
    def to_proto(cls, value: hh.EmployerArchivedVacanciesOrderEnum) -> proto.EmployerArchivedVacanciesOrder.ValueType:
        return cls.EMPLOYER_ARCHIVED_VACANCIES_ORDER_PROTO.get(
            value, proto.EMPLOYER_ARCHIVED_VACANCIES_ORDER_UNSPECIFIED
        )

    @classmethod
    def to_python(
        cls, value: proto.EmployerArchivedVacanciesOrder.ValueType
    ) -> hh.EmployerArchivedVacanciesOrderEnum | None:
        return cls.EMPLOYER_ARCHIVED_VACANCIES_ORDER_PYTHON.get(value, None)


@final
class EmployerHiddenVacanciesOrderMapper:
    EMPLOYER_HIDDEN_VACANCIES_ORDER_PROTO: ClassVar[
        dict[hh.EmployerHiddenVacanciesOrderEnum, proto.EmployerHiddenVacanciesOrder.ValueType]
    ] = {
        hh.EmployerHiddenVacanciesOrderEnum.NAME_ASC: proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_NAME_ASC,
        hh.EmployerHiddenVacanciesOrderEnum.NAME_DESC: proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_NAME_DESC,
        hh.EmployerHiddenVacanciesOrderEnum.ARCHIVE_TIME_ASC: proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_ARCHIVE_TIME_ASC,
        hh.EmployerHiddenVacanciesOrderEnum.ARCHIVE_TIME_DESC: proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_ARCHIVE_TIME_DESC,
    }
    EMPLOYER_HIDDEN_VACANCIES_ORDER_PYTHON: ClassVar[
        dict[proto.EmployerHiddenVacanciesOrder.ValueType, hh.EmployerHiddenVacanciesOrderEnum]
    ] = {
        proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_NAME_ASC: hh.EmployerHiddenVacanciesOrderEnum.NAME_ASC,
        proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_NAME_DESC: hh.EmployerHiddenVacanciesOrderEnum.NAME_DESC,
        proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_ARCHIVE_TIME_ASC: hh.EmployerHiddenVacanciesOrderEnum.ARCHIVE_TIME_ASC,
        proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_ARCHIVE_TIME_DESC: hh.EmployerHiddenVacanciesOrderEnum.ARCHIVE_TIME_DESC,
    }

    @classmethod
    def to_proto(cls, value: hh.EmployerHiddenVacanciesOrderEnum) -> proto.EmployerHiddenVacanciesOrder.ValueType:
        return cls.EMPLOYER_HIDDEN_VACANCIES_ORDER_PROTO.get(value, proto.EMPLOYER_HIDDEN_VACANCIES_ORDER_UNSPECIFIED)

    @classmethod
    def to_python(
        cls, value: proto.EmployerHiddenVacanciesOrder.ValueType
    ) -> hh.EmployerHiddenVacanciesOrderEnum | None:
        return cls.EMPLOYER_HIDDEN_VACANCIES_ORDER_PYTHON.get(value, None)


@final
class ApplicantCommentsOrderMapper:
    APPLICANT_COMMENTS_ORDER_PROTO: ClassVar[
        dict[hh.ApplicantCommentsOrderEnum, proto.ApplicantCommentsOrder.ValueType]
    ] = {
        hh.ApplicantCommentsOrderEnum.CREATION_TIME_DESC: proto.APPLICANT_COMMENTS_ORDER_CREATION_TIME_DESC,
        hh.ApplicantCommentsOrderEnum.CREATION_TIME_ASC: proto.APPLICANT_COMMENTS_ORDER_CREATION_TIME_ASC,
    }
    APPLICANT_COMMENTS_ORDER_PYTHON: ClassVar[
        dict[proto.ApplicantCommentsOrder.ValueType, hh.ApplicantCommentsOrderEnum]
    ] = {
        proto.APPLICANT_COMMENTS_ORDER_CREATION_TIME_DESC: hh.ApplicantCommentsOrderEnum.CREATION_TIME_DESC,
        proto.APPLICANT_COMMENTS_ORDER_CREATION_TIME_ASC: hh.ApplicantCommentsOrderEnum.CREATION_TIME_ASC,
    }

    @classmethod
    def to_proto(cls, value: hh.ApplicantCommentsOrderEnum) -> proto.ApplicantCommentsOrder.ValueType:
        return cls.APPLICANT_COMMENTS_ORDER_PROTO.get(value, proto.APPLICANT_COMMENTS_ORDER_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ApplicantCommentsOrder.ValueType) -> hh.ApplicantCommentsOrderEnum | None:
        return cls.APPLICANT_COMMENTS_ORDER_PYTHON.get(value, None)


@final
class VacancyNotProlongedReasonMapper:
    VACANCY_NOT_PROLONGED_REASON_PROTO: ClassVar[
        dict[hh.VacancyNotProlongedReasonEnum, proto.VacancyNotProlongedReason.ValueType]
    ] = {
        hh.VacancyNotProlongedReasonEnum.VACANCY_ARCHIVED: proto.VACANCY_NOT_PROLONGED_REASON_VACANCY_ARCHIVED,
        hh.VacancyNotProlongedReasonEnum.VACANCY_NOT_PREMODERATED: proto.VACANCY_NOT_PROLONGED_REASON_VACANCY_NOT_PREMODERATED,
        hh.VacancyNotProlongedReasonEnum.PFP_PUBLICATION_IS_UPDATED_AUTOMATICALLY: proto.VACANCY_NOT_PROLONGED_REASON_PFP_PUBLICATION_IS_UPDATED_AUTOMATICALLY,
        hh.VacancyNotProlongedReasonEnum.FREE_PROLONGATION_NOT_AVAILABLE: proto.VACANCY_NOT_PROLONGED_REASON_FREE_PROLONGATION_NOT_AVAILABLE,
        hh.VacancyNotProlongedReasonEnum.NOT_ENOUGH_QUOTAS: proto.VACANCY_NOT_PROLONGED_REASON_NOT_ENOUGH_QUOTAS,
        hh.VacancyNotProlongedReasonEnum.NOT_ENOUGH_PURCHASED_SERVICES: proto.VACANCY_NOT_PROLONGED_REASON_NOT_ENOUGH_PURCHASED_SERVICES,
        hh.VacancyNotProlongedReasonEnum.NOT_ENOUGH_DIVISION_SERVICES: proto.VACANCY_NOT_PROLONGED_REASON_NOT_ENOUGH_DIVISION_SERVICES,
        hh.VacancyNotProlongedReasonEnum.NOT_AVAILABLE_FOR_PURCHASE: proto.VACANCY_NOT_PROLONGED_REASON_NOT_AVAILABLE_FOR_PURCHASE,
        hh.VacancyNotProlongedReasonEnum.UNKNOWN: proto.VACANCY_NOT_PROLONGED_REASON_UNKNOWN,
    }
    VACANCY_NOT_PROLONGED_REASON_PYTHON: ClassVar[
        dict[proto.VacancyNotProlongedReason.ValueType, hh.VacancyNotProlongedReasonEnum]
    ] = {
        proto.VACANCY_NOT_PROLONGED_REASON_VACANCY_ARCHIVED: hh.VacancyNotProlongedReasonEnum.VACANCY_ARCHIVED,
        proto.VACANCY_NOT_PROLONGED_REASON_VACANCY_NOT_PREMODERATED: hh.VacancyNotProlongedReasonEnum.VACANCY_NOT_PREMODERATED,
        proto.VACANCY_NOT_PROLONGED_REASON_PFP_PUBLICATION_IS_UPDATED_AUTOMATICALLY: hh.VacancyNotProlongedReasonEnum.PFP_PUBLICATION_IS_UPDATED_AUTOMATICALLY,
        proto.VACANCY_NOT_PROLONGED_REASON_FREE_PROLONGATION_NOT_AVAILABLE: hh.VacancyNotProlongedReasonEnum.FREE_PROLONGATION_NOT_AVAILABLE,
        proto.VACANCY_NOT_PROLONGED_REASON_NOT_ENOUGH_QUOTAS: hh.VacancyNotProlongedReasonEnum.NOT_ENOUGH_QUOTAS,
        proto.VACANCY_NOT_PROLONGED_REASON_NOT_ENOUGH_PURCHASED_SERVICES: hh.VacancyNotProlongedReasonEnum.NOT_ENOUGH_PURCHASED_SERVICES,
        proto.VACANCY_NOT_PROLONGED_REASON_NOT_ENOUGH_DIVISION_SERVICES: hh.VacancyNotProlongedReasonEnum.NOT_ENOUGH_DIVISION_SERVICES,
        proto.VACANCY_NOT_PROLONGED_REASON_NOT_AVAILABLE_FOR_PURCHASE: hh.VacancyNotProlongedReasonEnum.NOT_AVAILABLE_FOR_PURCHASE,
        proto.VACANCY_NOT_PROLONGED_REASON_UNKNOWN: hh.VacancyNotProlongedReasonEnum.UNKNOWN,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancyNotProlongedReasonEnum) -> proto.VacancyNotProlongedReason.ValueType:
        return cls.VACANCY_NOT_PROLONGED_REASON_PROTO.get(value, proto.VACANCY_NOT_PROLONGED_REASON_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancyNotProlongedReason.ValueType) -> hh.VacancyNotProlongedReasonEnum | None:
        return cls.VACANCY_NOT_PROLONGED_REASON_PYTHON.get(value, None)


@final
class ResumeHiddenFieldsMapper:
    RESUME_HIDDEN_FIELDS_PROTO: ClassVar[dict[hh.ResumeHiddenFieldsEnum, proto.ResumeHiddenFields.ValueType]] = {
        hh.ResumeHiddenFieldsEnum.NAMES_AND_PHOTO: proto.RESUME_HIDDEN_FIELDS_NAMES_AND_PHOTO,
        hh.ResumeHiddenFieldsEnum.PHONES: proto.RESUME_HIDDEN_FIELDS_PHONES,
        hh.ResumeHiddenFieldsEnum.EMAIL: proto.RESUME_HIDDEN_FIELDS_EMAIL,
        hh.ResumeHiddenFieldsEnum.OTHER_CONTACTS: proto.RESUME_HIDDEN_FIELDS_OTHER_CONTACTS,
        hh.ResumeHiddenFieldsEnum.EXPERIENCE: proto.RESUME_HIDDEN_FIELDS_EXPERIENCE,
    }
    RESUME_HIDDEN_FIELDS_PYTHON: ClassVar[dict[proto.ResumeHiddenFields.ValueType, hh.ResumeHiddenFieldsEnum]] = {
        proto.RESUME_HIDDEN_FIELDS_NAMES_AND_PHOTO: hh.ResumeHiddenFieldsEnum.NAMES_AND_PHOTO,
        proto.RESUME_HIDDEN_FIELDS_PHONES: hh.ResumeHiddenFieldsEnum.PHONES,
        proto.RESUME_HIDDEN_FIELDS_EMAIL: hh.ResumeHiddenFieldsEnum.EMAIL,
        proto.RESUME_HIDDEN_FIELDS_OTHER_CONTACTS: hh.ResumeHiddenFieldsEnum.OTHER_CONTACTS,
        proto.RESUME_HIDDEN_FIELDS_EXPERIENCE: hh.ResumeHiddenFieldsEnum.EXPERIENCE,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeHiddenFieldsEnum) -> proto.ResumeHiddenFields.ValueType:
        return cls.RESUME_HIDDEN_FIELDS_PROTO.get(value, proto.RESUME_HIDDEN_FIELDS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeHiddenFields.ValueType) -> hh.ResumeHiddenFieldsEnum | None:
        return cls.RESUME_HIDDEN_FIELDS_PYTHON.get(value, None)


@final
class PhoneCallStatusMapper:
    PHONE_CALL_STATUS_PROTO: ClassVar[dict[hh.PhoneCallStatusEnum, proto.PhoneCallStatus.ValueType]] = {
        hh.PhoneCallStatusEnum.PICK_SUCCESSFUL: proto.PHONE_CALL_STATUS_PICK_SUCCESSFUL,
        hh.PhoneCallStatusEnum.CALLING: proto.PHONE_CALL_STATUS_CALLING,
        hh.PhoneCallStatusEnum.DID_NOT_CONNECT: proto.PHONE_CALL_STATUS_DID_NOT_CONNECT,
        hh.PhoneCallStatusEnum.CALL_IN_PROGRESS: proto.PHONE_CALL_STATUS_CALL_IN_PROGRESS,
        hh.PhoneCallStatusEnum.CALL_ERROR: proto.PHONE_CALL_STATUS_CALL_ERROR,
        hh.PhoneCallStatusEnum.CALL_ENDED: proto.PHONE_CALL_STATUS_CALL_ENDED,
    }
    PHONE_CALL_STATUS_PYTHON: ClassVar[dict[proto.PhoneCallStatus.ValueType, hh.PhoneCallStatusEnum]] = {
        proto.PHONE_CALL_STATUS_PICK_SUCCESSFUL: hh.PhoneCallStatusEnum.PICK_SUCCESSFUL,
        proto.PHONE_CALL_STATUS_CALLING: hh.PhoneCallStatusEnum.CALLING,
        proto.PHONE_CALL_STATUS_DID_NOT_CONNECT: hh.PhoneCallStatusEnum.DID_NOT_CONNECT,
        proto.PHONE_CALL_STATUS_CALL_IN_PROGRESS: hh.PhoneCallStatusEnum.CALL_IN_PROGRESS,
        proto.PHONE_CALL_STATUS_CALL_ERROR: hh.PhoneCallStatusEnum.CALL_ERROR,
        proto.PHONE_CALL_STATUS_CALL_ENDED: hh.PhoneCallStatusEnum.CALL_ENDED,
    }

    @classmethod
    def to_proto(cls, value: hh.PhoneCallStatusEnum) -> proto.PhoneCallStatus.ValueType:
        return cls.PHONE_CALL_STATUS_PROTO.get(value, proto.PHONE_CALL_STATUS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.PhoneCallStatus.ValueType) -> hh.PhoneCallStatusEnum | None:
        return cls.PHONE_CALL_STATUS_PYTHON.get(value, None)


@final
class LinkedSocialsMapper:
    LINKED_SOCIALS_PROTO: ClassVar[dict[hh.LinkedSocialsEnum, proto.LinkedSocials.ValueType]] = {
        hh.LinkedSocialsEnum.ESIA: proto.LINKED_SOCIALS_ESIA,
        hh.LinkedSocialsEnum.VK: proto.LINKED_SOCIALS_VK,
        hh.LinkedSocialsEnum.GPLUS: proto.LINKED_SOCIALS_GPLUS,
        hh.LinkedSocialsEnum.MAIL: proto.LINKED_SOCIALS_MAIL,
        hh.LinkedSocialsEnum.OK: proto.LINKED_SOCIALS_OK,
        hh.LinkedSocialsEnum.APPLE: proto.LINKED_SOCIALS_APPLE,
        hh.LinkedSocialsEnum.LI: proto.LINKED_SOCIALS_LI,
        hh.LinkedSocialsEnum.FB: proto.LINKED_SOCIALS_FB,
        hh.LinkedSocialsEnum.TINKOFF_BUSINESS: proto.LINKED_SOCIALS_TINKOFF_BUSINESS,
        hh.LinkedSocialsEnum.TUTBY: proto.LINKED_SOCIALS_TUTBY,
        hh.LinkedSocialsEnum.RSV: proto.LINKED_SOCIALS_RSV,
        hh.LinkedSocialsEnum.VR: proto.LINKED_SOCIALS_VR,
    }
    LINKED_SOCIALS_PYTHON: ClassVar[dict[proto.LinkedSocials.ValueType, hh.LinkedSocialsEnum]] = {
        proto.LINKED_SOCIALS_ESIA: hh.LinkedSocialsEnum.ESIA,
        proto.LINKED_SOCIALS_VK: hh.LinkedSocialsEnum.VK,
        proto.LINKED_SOCIALS_GPLUS: hh.LinkedSocialsEnum.GPLUS,
        proto.LINKED_SOCIALS_MAIL: hh.LinkedSocialsEnum.MAIL,
        proto.LINKED_SOCIALS_OK: hh.LinkedSocialsEnum.OK,
        proto.LINKED_SOCIALS_APPLE: hh.LinkedSocialsEnum.APPLE,
        proto.LINKED_SOCIALS_LI: hh.LinkedSocialsEnum.LI,
        proto.LINKED_SOCIALS_FB: hh.LinkedSocialsEnum.FB,
        proto.LINKED_SOCIALS_TINKOFF_BUSINESS: hh.LinkedSocialsEnum.TINKOFF_BUSINESS,
        proto.LINKED_SOCIALS_TUTBY: hh.LinkedSocialsEnum.TUTBY,
        proto.LINKED_SOCIALS_RSV: hh.LinkedSocialsEnum.RSV,
        proto.LINKED_SOCIALS_VR: hh.LinkedSocialsEnum.VR,
    }

    @classmethod
    def to_proto(cls, value: hh.LinkedSocialsEnum) -> proto.LinkedSocials.ValueType:
        return cls.LINKED_SOCIALS_PROTO.get(value, proto.LINKED_SOCIALS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.LinkedSocials.ValueType) -> hh.LinkedSocialsEnum | None:
        return cls.LINKED_SOCIALS_PYTHON.get(value, None)


@final
class VacancyLabelMapper:
    VACANCY_LABEL_PROTO: ClassVar[dict[hh.VacancyLabelEnum, proto.VacancyLabel.ValueType]] = {
        hh.VacancyLabelEnum.WITH_ADDRESS: proto.VACANCY_LABEL_WITH_ADDRESS,
        hh.VacancyLabelEnum.ACCEPT_HANDICAPPED: proto.VACANCY_LABEL_ACCEPT_HANDICAPPED,
        hh.VacancyLabelEnum.NOT_FROM_AGENCY: proto.VACANCY_LABEL_NOT_FROM_AGENCY,
        hh.VacancyLabelEnum.ACCEPT_KIDS: proto.VACANCY_LABEL_ACCEPT_KIDS,
        hh.VacancyLabelEnum.ACCREDITED_IT: proto.VACANCY_LABEL_ACCREDITED_IT,
        hh.VacancyLabelEnum.LOW_PERFORMANCE: proto.VACANCY_LABEL_LOW_PERFORMANCE,
        hh.VacancyLabelEnum.INTERNSHIP: proto.VACANCY_LABEL_INTERNSHIP,
        hh.VacancyLabelEnum.NIGHT_SHIFTS: proto.VACANCY_LABEL_NIGHT_SHIFTS,
        hh.VacancyLabelEnum.WITH_SALARY: proto.VACANCY_LABEL_WITH_SALARY,
        hh.VacancyLabelEnum.ACCEPT_TEENS: proto.VACANCY_LABEL_ACCEPT_TEENS,
    }
    VACANCY_LABEL_PYTHON: ClassVar[dict[proto.VacancyLabel.ValueType, hh.VacancyLabelEnum]] = {
        proto.VACANCY_LABEL_WITH_ADDRESS: hh.VacancyLabelEnum.WITH_ADDRESS,
        proto.VACANCY_LABEL_ACCEPT_HANDICAPPED: hh.VacancyLabelEnum.ACCEPT_HANDICAPPED,
        proto.VACANCY_LABEL_NOT_FROM_AGENCY: hh.VacancyLabelEnum.NOT_FROM_AGENCY,
        proto.VACANCY_LABEL_ACCEPT_KIDS: hh.VacancyLabelEnum.ACCEPT_KIDS,
        proto.VACANCY_LABEL_ACCREDITED_IT: hh.VacancyLabelEnum.ACCREDITED_IT,
        proto.VACANCY_LABEL_LOW_PERFORMANCE: hh.VacancyLabelEnum.LOW_PERFORMANCE,
        proto.VACANCY_LABEL_INTERNSHIP: hh.VacancyLabelEnum.INTERNSHIP,
        proto.VACANCY_LABEL_NIGHT_SHIFTS: hh.VacancyLabelEnum.NIGHT_SHIFTS,
        proto.VACANCY_LABEL_WITH_SALARY: hh.VacancyLabelEnum.WITH_SALARY,
        proto.VACANCY_LABEL_ACCEPT_TEENS: hh.VacancyLabelEnum.ACCEPT_TEENS,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancyLabelEnum) -> proto.VacancyLabel.ValueType:
        return cls.VACANCY_LABEL_PROTO.get(value, proto.VACANCY_LABEL_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancyLabel.ValueType) -> hh.VacancyLabelEnum | None:
        return cls.VACANCY_LABEL_PYTHON.get(value, None)


@final
class ExperienceMapper:
    EXPERIENCE_PROTO: ClassVar[dict[hh.ExperienceEnum, proto.Experience.ValueType]] = {
        hh.ExperienceEnum.NOEXPERIENCE: proto.EXPERIENCE_NOEXPERIENCE,
        hh.ExperienceEnum.BETWEEN1AND3: proto.EXPERIENCE_BETWEEN1AND3,
        hh.ExperienceEnum.BETWEEN3AND6: proto.EXPERIENCE_BETWEEN3AND6,
        hh.ExperienceEnum.MORETHAN6: proto.EXPERIENCE_MORETHAN6,
    }
    EXPERIENCE_PYTHON: ClassVar[dict[proto.Experience.ValueType, hh.ExperienceEnum]] = {
        proto.EXPERIENCE_NOEXPERIENCE: hh.ExperienceEnum.NOEXPERIENCE,
        proto.EXPERIENCE_BETWEEN1AND3: hh.ExperienceEnum.BETWEEN1AND3,
        proto.EXPERIENCE_BETWEEN3AND6: hh.ExperienceEnum.BETWEEN3AND6,
        proto.EXPERIENCE_MORETHAN6: hh.ExperienceEnum.MORETHAN6,
    }

    @classmethod
    def to_proto(cls, value: hh.ExperienceEnum) -> proto.Experience.ValueType:
        return cls.EXPERIENCE_PROTO.get(value, proto.EXPERIENCE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.Experience.ValueType) -> hh.ExperienceEnum | None:
        return cls.EXPERIENCE_PYTHON.get(value, None)


@final
class EmploymentMapper:
    EMPLOYMENT_PROTO: ClassVar[dict[hh.EmploymentEnum, proto.Employment.ValueType]] = {
        hh.EmploymentEnum.FULL: proto.EMPLOYMENT_FULL,
        hh.EmploymentEnum.PART: proto.EMPLOYMENT_PART,
        hh.EmploymentEnum.PROJECT: proto.EMPLOYMENT_PROJECT,
        hh.EmploymentEnum.VOLUNTEER: proto.EMPLOYMENT_VOLUNTEER,
        hh.EmploymentEnum.PROBATION: proto.EMPLOYMENT_PROBATION,
    }
    EMPLOYMENT_PYTHON: ClassVar[dict[proto.Employment.ValueType, hh.EmploymentEnum]] = {
        proto.EMPLOYMENT_FULL: hh.EmploymentEnum.FULL,
        proto.EMPLOYMENT_PART: hh.EmploymentEnum.PART,
        proto.EMPLOYMENT_PROJECT: hh.EmploymentEnum.PROJECT,
        proto.EMPLOYMENT_VOLUNTEER: hh.EmploymentEnum.VOLUNTEER,
        proto.EMPLOYMENT_PROBATION: hh.EmploymentEnum.PROBATION,
    }

    @classmethod
    def to_proto(cls, value: hh.EmploymentEnum) -> proto.Employment.ValueType:
        return cls.EMPLOYMENT_PROTO.get(value, proto.EMPLOYMENT_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.Employment.ValueType) -> hh.EmploymentEnum | None:
        return cls.EMPLOYMENT_PYTHON.get(value, None)


@final
class ScheduleMapper:
    SCHEDULE_PROTO: ClassVar[dict[hh.ScheduleEnum, proto.Schedule.ValueType]] = {
        hh.ScheduleEnum.FULLDAY: proto.SCHEDULE_FULLDAY,
        hh.ScheduleEnum.SHIFT: proto.SCHEDULE_SHIFT,
        hh.ScheduleEnum.FLEXIBLE: proto.SCHEDULE_FLEXIBLE,
        hh.ScheduleEnum.REMOTE: proto.SCHEDULE_REMOTE,
        hh.ScheduleEnum.FLYINFLYOUT: proto.SCHEDULE_FLYINFLYOUT,
    }
    SCHEDULE_PYTHON: ClassVar[dict[proto.Schedule.ValueType, hh.ScheduleEnum]] = {
        proto.SCHEDULE_FULLDAY: hh.ScheduleEnum.FULLDAY,
        proto.SCHEDULE_SHIFT: hh.ScheduleEnum.SHIFT,
        proto.SCHEDULE_FLEXIBLE: hh.ScheduleEnum.FLEXIBLE,
        proto.SCHEDULE_REMOTE: hh.ScheduleEnum.REMOTE,
        proto.SCHEDULE_FLYINFLYOUT: hh.ScheduleEnum.FLYINFLYOUT,
    }

    @classmethod
    def to_proto(cls, value: hh.ScheduleEnum) -> proto.Schedule.ValueType:
        return cls.SCHEDULE_PROTO.get(value, proto.SCHEDULE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.Schedule.ValueType) -> hh.ScheduleEnum | None:
        return cls.SCHEDULE_PYTHON.get(value, None)


@final
class EducationLevelMapper:
    EDUCATION_LEVEL_PROTO: ClassVar[dict[hh.EducationLevelEnum, proto.EducationLevel.ValueType]] = {
        hh.EducationLevelEnum.SECONDARY: proto.EDUCATION_LEVEL_SECONDARY,
        hh.EducationLevelEnum.SPECIAL_SECONDARY: proto.EDUCATION_LEVEL_SPECIAL_SECONDARY,
        hh.EducationLevelEnum.UNFINISHED_HIGHER: proto.EDUCATION_LEVEL_UNFINISHED_HIGHER,
        hh.EducationLevelEnum.HIGHER: proto.EDUCATION_LEVEL_HIGHER,
        hh.EducationLevelEnum.BACHELOR: proto.EDUCATION_LEVEL_BACHELOR,
        hh.EducationLevelEnum.MASTER: proto.EDUCATION_LEVEL_MASTER,
        hh.EducationLevelEnum.CANDIDATE: proto.EDUCATION_LEVEL_CANDIDATE,
        hh.EducationLevelEnum.DOCTOR: proto.EDUCATION_LEVEL_DOCTOR,
    }
    EDUCATION_LEVEL_PYTHON: ClassVar[dict[proto.EducationLevel.ValueType, hh.EducationLevelEnum]] = {
        proto.EDUCATION_LEVEL_SECONDARY: hh.EducationLevelEnum.SECONDARY,
        proto.EDUCATION_LEVEL_SPECIAL_SECONDARY: hh.EducationLevelEnum.SPECIAL_SECONDARY,
        proto.EDUCATION_LEVEL_UNFINISHED_HIGHER: hh.EducationLevelEnum.UNFINISHED_HIGHER,
        proto.EDUCATION_LEVEL_HIGHER: hh.EducationLevelEnum.HIGHER,
        proto.EDUCATION_LEVEL_BACHELOR: hh.EducationLevelEnum.BACHELOR,
        proto.EDUCATION_LEVEL_MASTER: hh.EducationLevelEnum.MASTER,
        proto.EDUCATION_LEVEL_CANDIDATE: hh.EducationLevelEnum.CANDIDATE,
        proto.EDUCATION_LEVEL_DOCTOR: hh.EducationLevelEnum.DOCTOR,
    }

    @classmethod
    def to_proto(cls, value: hh.EducationLevelEnum) -> proto.EducationLevel.ValueType:
        return cls.EDUCATION_LEVEL_PROTO.get(value, proto.EDUCATION_LEVEL_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.EducationLevel.ValueType) -> hh.EducationLevelEnum | None:
        return cls.EDUCATION_LEVEL_PYTHON.get(value, None)


@final
class CurrencyMapper:
    CURRENCY_PROTO: ClassVar[dict[hh.CurrencyEnum, proto.Currency.ValueType]] = {
        hh.CurrencyEnum.AZN: proto.CURRENCY_AZN,
        hh.CurrencyEnum.BYR: proto.CURRENCY_BYR,
        hh.CurrencyEnum.EUR: proto.CURRENCY_EUR,
        hh.CurrencyEnum.GEL: proto.CURRENCY_GEL,
        hh.CurrencyEnum.KGS: proto.CURRENCY_KGS,
        hh.CurrencyEnum.KZT: proto.CURRENCY_KZT,
        hh.CurrencyEnum.RUR: proto.CURRENCY_RUR,
        hh.CurrencyEnum.UAH: proto.CURRENCY_UAH,
        hh.CurrencyEnum.USD: proto.CURRENCY_USD,
        hh.CurrencyEnum.UZS: proto.CURRENCY_UZS,
    }
    CURRENCY_PYTHON: ClassVar[dict[proto.Currency.ValueType, hh.CurrencyEnum]] = {
        proto.CURRENCY_AZN: hh.CurrencyEnum.AZN,
        proto.CURRENCY_BYR: hh.CurrencyEnum.BYR,
        proto.CURRENCY_EUR: hh.CurrencyEnum.EUR,
        proto.CURRENCY_GEL: hh.CurrencyEnum.GEL,
        proto.CURRENCY_KGS: hh.CurrencyEnum.KGS,
        proto.CURRENCY_KZT: hh.CurrencyEnum.KZT,
        proto.CURRENCY_RUR: hh.CurrencyEnum.RUR,
        proto.CURRENCY_UAH: hh.CurrencyEnum.UAH,
        proto.CURRENCY_USD: hh.CurrencyEnum.USD,
        proto.CURRENCY_UZS: hh.CurrencyEnum.UZS,
    }

    @classmethod
    def to_proto(cls, value: hh.CurrencyEnum) -> proto.Currency.ValueType:
        return cls.CURRENCY_PROTO.get(value, proto.CURRENCY_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.Currency.ValueType) -> hh.CurrencyEnum | None:
        return cls.CURRENCY_PYTHON.get(value, None)


@final
class VacancyBillingTypeMapper:
    VACANCY_BILLING_TYPE_PROTO: ClassVar[dict[hh.VacancyBillingTypeEnum, proto.VacancyBillingType.ValueType]] = {
        hh.VacancyBillingTypeEnum.FREE: proto.VACANCY_BILLING_TYPE_FREE,
        hh.VacancyBillingTypeEnum.STANDARD: proto.VACANCY_BILLING_TYPE_STANDARD,
        hh.VacancyBillingTypeEnum.STANDARD_PLUS: proto.VACANCY_BILLING_TYPE_STANDARD_PLUS,
        hh.VacancyBillingTypeEnum.PREMIUM: proto.VACANCY_BILLING_TYPE_PREMIUM,
    }
    VACANCY_BILLING_TYPE_PYTHON: ClassVar[dict[proto.VacancyBillingType.ValueType, hh.VacancyBillingTypeEnum]] = {
        proto.VACANCY_BILLING_TYPE_FREE: hh.VacancyBillingTypeEnum.FREE,
        proto.VACANCY_BILLING_TYPE_STANDARD: hh.VacancyBillingTypeEnum.STANDARD,
        proto.VACANCY_BILLING_TYPE_STANDARD_PLUS: hh.VacancyBillingTypeEnum.STANDARD_PLUS,
        proto.VACANCY_BILLING_TYPE_PREMIUM: hh.VacancyBillingTypeEnum.PREMIUM,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancyBillingTypeEnum) -> proto.VacancyBillingType.ValueType:
        return cls.VACANCY_BILLING_TYPE_PROTO.get(value, proto.VACANCY_BILLING_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancyBillingType.ValueType) -> hh.VacancyBillingTypeEnum | None:
        return cls.VACANCY_BILLING_TYPE_PYTHON.get(value, None)


@final
class ApplicantCommentAccessTypeMapper:
    APPLICANT_COMMENT_ACCESS_TYPE_PROTO: ClassVar[
        dict[hh.ApplicantCommentAccessTypeEnum, proto.ApplicantCommentAccessType.ValueType]
    ] = {
        hh.ApplicantCommentAccessTypeEnum.COWORKERS: proto.APPLICANT_COMMENT_ACCESS_TYPE_COWORKERS,
        hh.ApplicantCommentAccessTypeEnum.OWNER: proto.APPLICANT_COMMENT_ACCESS_TYPE_OWNER,
    }
    APPLICANT_COMMENT_ACCESS_TYPE_PYTHON: ClassVar[
        dict[proto.ApplicantCommentAccessType.ValueType, hh.ApplicantCommentAccessTypeEnum]
    ] = {
        proto.APPLICANT_COMMENT_ACCESS_TYPE_COWORKERS: hh.ApplicantCommentAccessTypeEnum.COWORKERS,
        proto.APPLICANT_COMMENT_ACCESS_TYPE_OWNER: hh.ApplicantCommentAccessTypeEnum.OWNER,
    }

    @classmethod
    def to_proto(cls, value: hh.ApplicantCommentAccessTypeEnum) -> proto.ApplicantCommentAccessType.ValueType:
        return cls.APPLICANT_COMMENT_ACCESS_TYPE_PROTO.get(value, proto.APPLICANT_COMMENT_ACCESS_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ApplicantCommentAccessType.ValueType) -> hh.ApplicantCommentAccessTypeEnum | None:
        return cls.APPLICANT_COMMENT_ACCESS_TYPE_PYTHON.get(value, None)


@final
class VacancyClusterMapper:
    VACANCY_CLUSTER_PROTO: ClassVar[dict[hh.VacancyClusterEnum, proto.VacancyCluster.ValueType]] = {
        hh.VacancyClusterEnum.AREA: proto.VACANCY_CLUSTER_AREA,
        hh.VacancyClusterEnum.METRO: proto.VACANCY_CLUSTER_METRO,
        hh.VacancyClusterEnum.SALARY: proto.VACANCY_CLUSTER_SALARY,
        hh.VacancyClusterEnum.INDUSTRY: proto.VACANCY_CLUSTER_INDUSTRY,
        hh.VacancyClusterEnum.SUB_INDUSTRY: proto.VACANCY_CLUSTER_SUB_INDUSTRY,
        hh.VacancyClusterEnum.EXPERIENCE: proto.VACANCY_CLUSTER_EXPERIENCE,
        hh.VacancyClusterEnum.LABEL: proto.VACANCY_CLUSTER_LABEL,
        hh.VacancyClusterEnum.PROFESSIONAL_ROLE: proto.VACANCY_CLUSTER_PROFESSIONAL_ROLE,
        hh.VacancyClusterEnum.DISTRICT: proto.VACANCY_CLUSTER_DISTRICT,
        hh.VacancyClusterEnum.EDUCATION: proto.VACANCY_CLUSTER_EDUCATION,
        hh.VacancyClusterEnum.ACCEPT_TEMPORARY: proto.VACANCY_CLUSTER_ACCEPT_TEMPORARY,
        hh.VacancyClusterEnum.EMPLOYMENT_FORM: proto.VACANCY_CLUSTER_EMPLOYMENT_FORM,
        hh.VacancyClusterEnum.WORK_SCHEDULE_BY_DAYS: proto.VACANCY_CLUSTER_WORK_SCHEDULE_BY_DAYS,
        hh.VacancyClusterEnum.WORKING_HOURS: proto.VACANCY_CLUSTER_WORKING_HOURS,
        hh.VacancyClusterEnum.WORK_FORMAT: proto.VACANCY_CLUSTER_WORK_FORMAT,
        hh.VacancyClusterEnum.SALARY_FREQUENCY: proto.VACANCY_CLUSTER_SALARY_FREQUENCY,
        hh.VacancyClusterEnum.SALARY_PER_MODE: proto.VACANCY_CLUSTER_SALARY_PER_MODE,
        hh.VacancyClusterEnum.DRIVER_LICENSE_TYPES: proto.VACANCY_CLUSTER_DRIVER_LICENSE_TYPES,
    }
    VACANCY_CLUSTER_PYTHON: ClassVar[dict[proto.VacancyCluster.ValueType, hh.VacancyClusterEnum]] = {
        proto.VACANCY_CLUSTER_AREA: hh.VacancyClusterEnum.AREA,
        proto.VACANCY_CLUSTER_METRO: hh.VacancyClusterEnum.METRO,
        proto.VACANCY_CLUSTER_SALARY: hh.VacancyClusterEnum.SALARY,
        proto.VACANCY_CLUSTER_INDUSTRY: hh.VacancyClusterEnum.INDUSTRY,
        proto.VACANCY_CLUSTER_SUB_INDUSTRY: hh.VacancyClusterEnum.SUB_INDUSTRY,
        proto.VACANCY_CLUSTER_EXPERIENCE: hh.VacancyClusterEnum.EXPERIENCE,
        proto.VACANCY_CLUSTER_LABEL: hh.VacancyClusterEnum.LABEL,
        proto.VACANCY_CLUSTER_PROFESSIONAL_ROLE: hh.VacancyClusterEnum.PROFESSIONAL_ROLE,
        proto.VACANCY_CLUSTER_DISTRICT: hh.VacancyClusterEnum.DISTRICT,
        proto.VACANCY_CLUSTER_EDUCATION: hh.VacancyClusterEnum.EDUCATION,
        proto.VACANCY_CLUSTER_ACCEPT_TEMPORARY: hh.VacancyClusterEnum.ACCEPT_TEMPORARY,
        proto.VACANCY_CLUSTER_EMPLOYMENT_FORM: hh.VacancyClusterEnum.EMPLOYMENT_FORM,
        proto.VACANCY_CLUSTER_WORK_SCHEDULE_BY_DAYS: hh.VacancyClusterEnum.WORK_SCHEDULE_BY_DAYS,
        proto.VACANCY_CLUSTER_WORKING_HOURS: hh.VacancyClusterEnum.WORKING_HOURS,
        proto.VACANCY_CLUSTER_WORK_FORMAT: hh.VacancyClusterEnum.WORK_FORMAT,
        proto.VACANCY_CLUSTER_SALARY_FREQUENCY: hh.VacancyClusterEnum.SALARY_FREQUENCY,
        proto.VACANCY_CLUSTER_SALARY_PER_MODE: hh.VacancyClusterEnum.SALARY_PER_MODE,
        proto.VACANCY_CLUSTER_DRIVER_LICENSE_TYPES: hh.VacancyClusterEnum.DRIVER_LICENSE_TYPES,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancyClusterEnum) -> proto.VacancyCluster.ValueType:
        return cls.VACANCY_CLUSTER_PROTO.get(value, proto.VACANCY_CLUSTER_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancyCluster.ValueType) -> hh.VacancyClusterEnum | None:
        return cls.VACANCY_CLUSTER_PYTHON.get(value, None)


@final
class DriverLicenseTypesMapper:
    DRIVER_LICENSE_TYPES_PROTO: ClassVar[dict[hh.DriverLicenseTypesEnum, proto.DriverLicenseTypes.ValueType]] = {
        hh.DriverLicenseTypesEnum.A: proto.DRIVER_LICENSE_TYPES_A,
        hh.DriverLicenseTypesEnum.B: proto.DRIVER_LICENSE_TYPES_B,
        hh.DriverLicenseTypesEnum.C: proto.DRIVER_LICENSE_TYPES_C,
        hh.DriverLicenseTypesEnum.D: proto.DRIVER_LICENSE_TYPES_D,
        hh.DriverLicenseTypesEnum.E: proto.DRIVER_LICENSE_TYPES_E,
        hh.DriverLicenseTypesEnum.BE: proto.DRIVER_LICENSE_TYPES_BE,
        hh.DriverLicenseTypesEnum.CE: proto.DRIVER_LICENSE_TYPES_CE,
        hh.DriverLicenseTypesEnum.DE: proto.DRIVER_LICENSE_TYPES_DE,
        hh.DriverLicenseTypesEnum.TM: proto.DRIVER_LICENSE_TYPES_TM,
        hh.DriverLicenseTypesEnum.TB: proto.DRIVER_LICENSE_TYPES_TB,
    }
    DRIVER_LICENSE_TYPES_PYTHON: ClassVar[dict[proto.DriverLicenseTypes.ValueType, hh.DriverLicenseTypesEnum]] = {
        proto.DRIVER_LICENSE_TYPES_A: hh.DriverLicenseTypesEnum.A,
        proto.DRIVER_LICENSE_TYPES_B: hh.DriverLicenseTypesEnum.B,
        proto.DRIVER_LICENSE_TYPES_C: hh.DriverLicenseTypesEnum.C,
        proto.DRIVER_LICENSE_TYPES_D: hh.DriverLicenseTypesEnum.D,
        proto.DRIVER_LICENSE_TYPES_E: hh.DriverLicenseTypesEnum.E,
        proto.DRIVER_LICENSE_TYPES_BE: hh.DriverLicenseTypesEnum.BE,
        proto.DRIVER_LICENSE_TYPES_CE: hh.DriverLicenseTypesEnum.CE,
        proto.DRIVER_LICENSE_TYPES_DE: hh.DriverLicenseTypesEnum.DE,
        proto.DRIVER_LICENSE_TYPES_TM: hh.DriverLicenseTypesEnum.TM,
        proto.DRIVER_LICENSE_TYPES_TB: hh.DriverLicenseTypesEnum.TB,
    }

    @classmethod
    def to_proto(cls, value: hh.DriverLicenseTypesEnum) -> proto.DriverLicenseTypes.ValueType:
        return cls.DRIVER_LICENSE_TYPES_PROTO.get(value, proto.DRIVER_LICENSE_TYPES_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.DriverLicenseTypes.ValueType) -> hh.DriverLicenseTypesEnum | None:
        return cls.DRIVER_LICENSE_TYPES_PYTHON.get(value, None)


@final
class LanguageLevelMapper:
    LANGUAGE_LEVEL_PROTO: ClassVar[dict[hh.LanguageLevelEnum, proto.LanguageLevel.ValueType]] = {
        hh.LanguageLevelEnum.A1: proto.LANGUAGE_LEVEL_A1,
        hh.LanguageLevelEnum.A2: proto.LANGUAGE_LEVEL_A2,
        hh.LanguageLevelEnum.B1: proto.LANGUAGE_LEVEL_B1,
        hh.LanguageLevelEnum.B2: proto.LANGUAGE_LEVEL_B2,
        hh.LanguageLevelEnum.C1: proto.LANGUAGE_LEVEL_C1,
        hh.LanguageLevelEnum.C2: proto.LANGUAGE_LEVEL_C2,
        hh.LanguageLevelEnum.L1: proto.LANGUAGE_LEVEL_L1,
    }
    LANGUAGE_LEVEL_PYTHON: ClassVar[dict[proto.LanguageLevel.ValueType, hh.LanguageLevelEnum]] = {
        proto.LANGUAGE_LEVEL_A1: hh.LanguageLevelEnum.A1,
        proto.LANGUAGE_LEVEL_A2: hh.LanguageLevelEnum.A2,
        proto.LANGUAGE_LEVEL_B1: hh.LanguageLevelEnum.B1,
        proto.LANGUAGE_LEVEL_B2: hh.LanguageLevelEnum.B2,
        proto.LANGUAGE_LEVEL_C1: hh.LanguageLevelEnum.C1,
        proto.LANGUAGE_LEVEL_C2: hh.LanguageLevelEnum.C2,
        proto.LANGUAGE_LEVEL_L1: hh.LanguageLevelEnum.L1,
    }

    @classmethod
    def to_proto(cls, value: hh.LanguageLevelEnum) -> proto.LanguageLevel.ValueType:
        return cls.LANGUAGE_LEVEL_PROTO.get(value, proto.LANGUAGE_LEVEL_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.LanguageLevel.ValueType) -> hh.LanguageLevelEnum | None:
        return cls.LANGUAGE_LEVEL_PYTHON.get(value, None)


@final
class WorkingDaysMapper:
    WORKING_DAYS_PROTO: ClassVar[dict[hh.WorkingDaysEnum, proto.WorkingDays.ValueType]] = {
        hh.WorkingDaysEnum.ONLY_SATURDAY_AND_SUNDAY: proto.WORKING_DAYS_ONLY_SATURDAY_AND_SUNDAY,
    }
    WORKING_DAYS_PYTHON: ClassVar[dict[proto.WorkingDays.ValueType, hh.WorkingDaysEnum]] = {
        proto.WORKING_DAYS_ONLY_SATURDAY_AND_SUNDAY: hh.WorkingDaysEnum.ONLY_SATURDAY_AND_SUNDAY,
    }

    @classmethod
    def to_proto(cls, value: hh.WorkingDaysEnum) -> proto.WorkingDays.ValueType:
        return cls.WORKING_DAYS_PROTO.get(value, proto.WORKING_DAYS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.WorkingDays.ValueType) -> hh.WorkingDaysEnum | None:
        return cls.WORKING_DAYS_PYTHON.get(value, None)


@final
class WorkingTimeIntervalsMapper:
    WORKING_TIME_INTERVALS_PROTO: ClassVar[dict[hh.WorkingTimeIntervalsEnum, proto.WorkingTimeIntervals.ValueType]] = {
        hh.WorkingTimeIntervalsEnum.FROM_FOUR_TO_SIX_HOURS_IN_A_DAY: proto.WORKING_TIME_INTERVALS_FROM_FOUR_TO_SIX_HOURS_IN_A_DAY,
    }
    WORKING_TIME_INTERVALS_PYTHON: ClassVar[dict[proto.WorkingTimeIntervals.ValueType, hh.WorkingTimeIntervalsEnum]] = {
        proto.WORKING_TIME_INTERVALS_FROM_FOUR_TO_SIX_HOURS_IN_A_DAY: hh.WorkingTimeIntervalsEnum.FROM_FOUR_TO_SIX_HOURS_IN_A_DAY,
    }

    @classmethod
    def to_proto(cls, value: hh.WorkingTimeIntervalsEnum) -> proto.WorkingTimeIntervals.ValueType:
        return cls.WORKING_TIME_INTERVALS_PROTO.get(value, proto.WORKING_TIME_INTERVALS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.WorkingTimeIntervals.ValueType) -> hh.WorkingTimeIntervalsEnum | None:
        return cls.WORKING_TIME_INTERVALS_PYTHON.get(value, None)


@final
class WorkingTimeModesMapper:
    WORKING_TIME_MODES_PROTO: ClassVar[dict[hh.WorkingTimeModesEnum, proto.WorkingTimeModes.ValueType]] = {
        hh.WorkingTimeModesEnum.START_AFTER_SIXTEEN: proto.WORKING_TIME_MODES_START_AFTER_SIXTEEN,
    }
    WORKING_TIME_MODES_PYTHON: ClassVar[dict[proto.WorkingTimeModes.ValueType, hh.WorkingTimeModesEnum]] = {
        proto.WORKING_TIME_MODES_START_AFTER_SIXTEEN: hh.WorkingTimeModesEnum.START_AFTER_SIXTEEN,
    }

    @classmethod
    def to_proto(cls, value: hh.WorkingTimeModesEnum) -> proto.WorkingTimeModes.ValueType:
        return cls.WORKING_TIME_MODES_PROTO.get(value, proto.WORKING_TIME_MODES_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.WorkingTimeModes.ValueType) -> hh.WorkingTimeModesEnum | None:
        return cls.WORKING_TIME_MODES_PYTHON.get(value, None)


@final
class VacancyTypeMapper:
    VACANCY_TYPE_PROTO: ClassVar[dict[hh.VacancyTypeEnum, proto.VacancyType.ValueType]] = {
        hh.VacancyTypeEnum.DIRECT: proto.VACANCY_TYPE_DIRECT,
        hh.VacancyTypeEnum.ANONYMOUS: proto.VACANCY_TYPE_ANONYMOUS,
        hh.VacancyTypeEnum.CLOSED: proto.VACANCY_TYPE_CLOSED,
        hh.VacancyTypeEnum.OPEN: proto.VACANCY_TYPE_OPEN,
    }
    VACANCY_TYPE_PYTHON: ClassVar[dict[proto.VacancyType.ValueType, hh.VacancyTypeEnum]] = {
        proto.VACANCY_TYPE_DIRECT: hh.VacancyTypeEnum.DIRECT,
        proto.VACANCY_TYPE_ANONYMOUS: hh.VacancyTypeEnum.ANONYMOUS,
        proto.VACANCY_TYPE_CLOSED: hh.VacancyTypeEnum.CLOSED,
        proto.VACANCY_TYPE_OPEN: hh.VacancyTypeEnum.OPEN,
    }

    @classmethod
    def to_proto(cls, value: hh.VacancyTypeEnum) -> proto.VacancyType.ValueType:
        return cls.VACANCY_TYPE_PROTO.get(value, proto.VACANCY_TYPE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.VacancyType.ValueType) -> hh.VacancyTypeEnum | None:
        return cls.VACANCY_TYPE_PYTHON.get(value, None)


@final
class JobSearchStatusesApplicantMapper:
    JOB_SEARCH_STATUSES_APPLICANT_PROTO: ClassVar[
        dict[hh.JobSearchStatusesApplicantEnum, proto.JobSearchStatusesApplicant.ValueType]
    ] = {
        hh.JobSearchStatusesApplicantEnum.ACTIVE_SEARCH: proto.JOB_SEARCH_STATUSES_APPLICANT_ACTIVE_SEARCH,
        hh.JobSearchStatusesApplicantEnum.LOOKING_FOR_OFFERS: proto.JOB_SEARCH_STATUSES_APPLICANT_LOOKING_FOR_OFFERS,
        hh.JobSearchStatusesApplicantEnum.NOT_LOOKING_FOR_JOB: proto.JOB_SEARCH_STATUSES_APPLICANT_NOT_LOOKING_FOR_JOB,
        hh.JobSearchStatusesApplicantEnum.HAS_JOB_OFFER: proto.JOB_SEARCH_STATUSES_APPLICANT_HAS_JOB_OFFER,
        hh.JobSearchStatusesApplicantEnum.ACCEPTED_JOB_OFFER: proto.JOB_SEARCH_STATUSES_APPLICANT_ACCEPTED_JOB_OFFER,
    }
    JOB_SEARCH_STATUSES_APPLICANT_PYTHON: ClassVar[
        dict[proto.JobSearchStatusesApplicant.ValueType, hh.JobSearchStatusesApplicantEnum]
    ] = {
        proto.JOB_SEARCH_STATUSES_APPLICANT_ACTIVE_SEARCH: hh.JobSearchStatusesApplicantEnum.ACTIVE_SEARCH,
        proto.JOB_SEARCH_STATUSES_APPLICANT_LOOKING_FOR_OFFERS: hh.JobSearchStatusesApplicantEnum.LOOKING_FOR_OFFERS,
        proto.JOB_SEARCH_STATUSES_APPLICANT_NOT_LOOKING_FOR_JOB: hh.JobSearchStatusesApplicantEnum.NOT_LOOKING_FOR_JOB,
        proto.JOB_SEARCH_STATUSES_APPLICANT_HAS_JOB_OFFER: hh.JobSearchStatusesApplicantEnum.HAS_JOB_OFFER,
        proto.JOB_SEARCH_STATUSES_APPLICANT_ACCEPTED_JOB_OFFER: hh.JobSearchStatusesApplicantEnum.ACCEPTED_JOB_OFFER,
    }

    @classmethod
    def to_proto(cls, value: hh.JobSearchStatusesApplicantEnum) -> proto.JobSearchStatusesApplicant.ValueType:
        return cls.JOB_SEARCH_STATUSES_APPLICANT_PROTO.get(value, proto.JOB_SEARCH_STATUSES_APPLICANT_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.JobSearchStatusesApplicant.ValueType) -> hh.JobSearchStatusesApplicantEnum | None:
        return cls.JOB_SEARCH_STATUSES_APPLICANT_PYTHON.get(value, None)


@final
class JobSearchStatusesEmployerMapper:
    JOB_SEARCH_STATUSES_EMPLOYER_PROTO: ClassVar[
        dict[hh.JobSearchStatusesEmployerEnum, proto.JobSearchStatusesEmployer.ValueType]
    ] = {
        hh.JobSearchStatusesEmployerEnum.ACTIVE_SEARCH: proto.JOB_SEARCH_STATUSES_EMPLOYER_ACTIVE_SEARCH,
        hh.JobSearchStatusesEmployerEnum.LOOKING_FOR_OFFERS: proto.JOB_SEARCH_STATUSES_EMPLOYER_LOOKING_FOR_OFFERS,
        hh.JobSearchStatusesEmployerEnum.NOT_LOOKING_FOR_JOB: proto.JOB_SEARCH_STATUSES_EMPLOYER_NOT_LOOKING_FOR_JOB,
        hh.JobSearchStatusesEmployerEnum.HAS_JOB_OFFER: proto.JOB_SEARCH_STATUSES_EMPLOYER_HAS_JOB_OFFER,
        hh.JobSearchStatusesEmployerEnum.ACCEPTED_JOB_OFFER: proto.JOB_SEARCH_STATUSES_EMPLOYER_ACCEPTED_JOB_OFFER,
    }
    JOB_SEARCH_STATUSES_EMPLOYER_PYTHON: ClassVar[
        dict[proto.JobSearchStatusesEmployer.ValueType, hh.JobSearchStatusesEmployerEnum]
    ] = {
        proto.JOB_SEARCH_STATUSES_EMPLOYER_ACTIVE_SEARCH: hh.JobSearchStatusesEmployerEnum.ACTIVE_SEARCH,
        proto.JOB_SEARCH_STATUSES_EMPLOYER_LOOKING_FOR_OFFERS: hh.JobSearchStatusesEmployerEnum.LOOKING_FOR_OFFERS,
        proto.JOB_SEARCH_STATUSES_EMPLOYER_NOT_LOOKING_FOR_JOB: hh.JobSearchStatusesEmployerEnum.NOT_LOOKING_FOR_JOB,
        proto.JOB_SEARCH_STATUSES_EMPLOYER_HAS_JOB_OFFER: hh.JobSearchStatusesEmployerEnum.HAS_JOB_OFFER,
        proto.JOB_SEARCH_STATUSES_EMPLOYER_ACCEPTED_JOB_OFFER: hh.JobSearchStatusesEmployerEnum.ACCEPTED_JOB_OFFER,
    }

    @classmethod
    def to_proto(cls, value: hh.JobSearchStatusesEmployerEnum) -> proto.JobSearchStatusesEmployer.ValueType:
        return cls.JOB_SEARCH_STATUSES_EMPLOYER_PROTO.get(value, proto.JOB_SEARCH_STATUSES_EMPLOYER_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.JobSearchStatusesEmployer.ValueType) -> hh.JobSearchStatusesEmployerEnum | None:
        return cls.JOB_SEARCH_STATUSES_EMPLOYER_PYTHON.get(value, None)


@final
class EmploymentFormMapper:
    EMPLOYMENT_FORM_PROTO: ClassVar[dict[hh.EmploymentFormEnum, proto.EmploymentForm.ValueType]] = {
        hh.EmploymentFormEnum.FULL: proto.EMPLOYMENT_FORM_FULL,
        hh.EmploymentFormEnum.PART: proto.EMPLOYMENT_FORM_PART,
        hh.EmploymentFormEnum.PROJECT: proto.EMPLOYMENT_FORM_PROJECT,
        hh.EmploymentFormEnum.FLY_IN_FLY_OUT: proto.EMPLOYMENT_FORM_FLY_IN_FLY_OUT,
        hh.EmploymentFormEnum.SIDE_JOB: proto.EMPLOYMENT_FORM_SIDE_JOB,
    }
    EMPLOYMENT_FORM_PYTHON: ClassVar[dict[proto.EmploymentForm.ValueType, hh.EmploymentFormEnum]] = {
        proto.EMPLOYMENT_FORM_FULL: hh.EmploymentFormEnum.FULL,
        proto.EMPLOYMENT_FORM_PART: hh.EmploymentFormEnum.PART,
        proto.EMPLOYMENT_FORM_PROJECT: hh.EmploymentFormEnum.PROJECT,
        proto.EMPLOYMENT_FORM_FLY_IN_FLY_OUT: hh.EmploymentFormEnum.FLY_IN_FLY_OUT,
        proto.EMPLOYMENT_FORM_SIDE_JOB: hh.EmploymentFormEnum.SIDE_JOB,
    }

    @classmethod
    def to_proto(cls, value: hh.EmploymentFormEnum) -> proto.EmploymentForm.ValueType:
        return cls.EMPLOYMENT_FORM_PROTO.get(value, proto.EMPLOYMENT_FORM_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.EmploymentForm.ValueType) -> hh.EmploymentFormEnum | None:
        return cls.EMPLOYMENT_FORM_PYTHON.get(value, None)


@final
class WorkFormatMapper:
    WORK_FORMAT_PROTO: ClassVar[dict[hh.WorkFormatEnum, proto.WorkFormat.ValueType]] = {
        hh.WorkFormatEnum.ON_SITE: proto.WORK_FORMAT_ON_SITE,
        hh.WorkFormatEnum.REMOTE: proto.WORK_FORMAT_REMOTE,
        hh.WorkFormatEnum.HYBRID: proto.WORK_FORMAT_HYBRID,
        hh.WorkFormatEnum.FIELD_WORK: proto.WORK_FORMAT_FIELD_WORK,
    }
    WORK_FORMAT_PYTHON: ClassVar[dict[proto.WorkFormat.ValueType, hh.WorkFormatEnum]] = {
        proto.WORK_FORMAT_ON_SITE: hh.WorkFormatEnum.ON_SITE,
        proto.WORK_FORMAT_REMOTE: hh.WorkFormatEnum.REMOTE,
        proto.WORK_FORMAT_HYBRID: hh.WorkFormatEnum.HYBRID,
        proto.WORK_FORMAT_FIELD_WORK: hh.WorkFormatEnum.FIELD_WORK,
    }

    @classmethod
    def to_proto(cls, value: hh.WorkFormatEnum) -> proto.WorkFormat.ValueType:
        return cls.WORK_FORMAT_PROTO.get(value, proto.WORK_FORMAT_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.WorkFormat.ValueType) -> hh.WorkFormatEnum | None:
        return cls.WORK_FORMAT_PYTHON.get(value, None)


@final
class ResumeEmploymentFormMapper:
    RESUME_EMPLOYMENT_FORM_PROTO: ClassVar[dict[hh.ResumeEmploymentFormEnum, proto.ResumeEmploymentForm.ValueType]] = {
        hh.ResumeEmploymentFormEnum.FULL: proto.RESUME_EMPLOYMENT_FORM_FULL,
        hh.ResumeEmploymentFormEnum.PART_TIME: proto.RESUME_EMPLOYMENT_FORM_PART_TIME,
        hh.ResumeEmploymentFormEnum.INTERNSHIP: proto.RESUME_EMPLOYMENT_FORM_INTERNSHIP,
        hh.ResumeEmploymentFormEnum.VOLUNTEER: proto.RESUME_EMPLOYMENT_FORM_VOLUNTEER,
    }
    RESUME_EMPLOYMENT_FORM_PYTHON: ClassVar[dict[proto.ResumeEmploymentForm.ValueType, hh.ResumeEmploymentFormEnum]] = {
        proto.RESUME_EMPLOYMENT_FORM_FULL: hh.ResumeEmploymentFormEnum.FULL,
        proto.RESUME_EMPLOYMENT_FORM_PART_TIME: hh.ResumeEmploymentFormEnum.PART_TIME,
        proto.RESUME_EMPLOYMENT_FORM_INTERNSHIP: hh.ResumeEmploymentFormEnum.INTERNSHIP,
        proto.RESUME_EMPLOYMENT_FORM_VOLUNTEER: hh.ResumeEmploymentFormEnum.VOLUNTEER,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeEmploymentFormEnum) -> proto.ResumeEmploymentForm.ValueType:
        return cls.RESUME_EMPLOYMENT_FORM_PROTO.get(value, proto.RESUME_EMPLOYMENT_FORM_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeEmploymentForm.ValueType) -> hh.ResumeEmploymentFormEnum | None:
        return cls.RESUME_EMPLOYMENT_FORM_PYTHON.get(value, None)


@final
class ResumeWorkFormatMapper:
    RESUME_WORK_FORMAT_PROTO: ClassVar[dict[hh.ResumeWorkFormatEnum, proto.ResumeWorkFormat.ValueType]] = {
        hh.ResumeWorkFormatEnum.ON_SITE: proto.RESUME_WORK_FORMAT_ON_SITE,
        hh.ResumeWorkFormatEnum.REMOTE: proto.RESUME_WORK_FORMAT_REMOTE,
        hh.ResumeWorkFormatEnum.HYBRID: proto.RESUME_WORK_FORMAT_HYBRID,
        hh.ResumeWorkFormatEnum.FIELD_WORK: proto.RESUME_WORK_FORMAT_FIELD_WORK,
        hh.ResumeWorkFormatEnum.FLY_IN_FLY_OUT: proto.RESUME_WORK_FORMAT_FLY_IN_FLY_OUT,
    }
    RESUME_WORK_FORMAT_PYTHON: ClassVar[dict[proto.ResumeWorkFormat.ValueType, hh.ResumeWorkFormatEnum]] = {
        proto.RESUME_WORK_FORMAT_ON_SITE: hh.ResumeWorkFormatEnum.ON_SITE,
        proto.RESUME_WORK_FORMAT_REMOTE: hh.ResumeWorkFormatEnum.REMOTE,
        proto.RESUME_WORK_FORMAT_HYBRID: hh.ResumeWorkFormatEnum.HYBRID,
        proto.RESUME_WORK_FORMAT_FIELD_WORK: hh.ResumeWorkFormatEnum.FIELD_WORK,
        proto.RESUME_WORK_FORMAT_FLY_IN_FLY_OUT: hh.ResumeWorkFormatEnum.FLY_IN_FLY_OUT,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeWorkFormatEnum) -> proto.ResumeWorkFormat.ValueType:
        return cls.RESUME_WORK_FORMAT_PROTO.get(value, proto.RESUME_WORK_FORMAT_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeWorkFormat.ValueType) -> hh.ResumeWorkFormatEnum | None:
        return cls.RESUME_WORK_FORMAT_PYTHON.get(value, None)


@final
class WorkingHoursMapper:
    WORKING_HOURS_PROTO: ClassVar[dict[hh.WorkingHoursEnum, proto.WorkingHours.ValueType]] = {
        hh.WorkingHoursEnum.HOURS_2: proto.WORKING_HOURS_HOURS_2,
        hh.WorkingHoursEnum.HOURS_3: proto.WORKING_HOURS_HOURS_3,
        hh.WorkingHoursEnum.HOURS_4: proto.WORKING_HOURS_HOURS_4,
        hh.WorkingHoursEnum.HOURS_5: proto.WORKING_HOURS_HOURS_5,
        hh.WorkingHoursEnum.HOURS_6: proto.WORKING_HOURS_HOURS_6,
        hh.WorkingHoursEnum.HOURS_7: proto.WORKING_HOURS_HOURS_7,
        hh.WorkingHoursEnum.HOURS_8: proto.WORKING_HOURS_HOURS_8,
        hh.WorkingHoursEnum.HOURS_9: proto.WORKING_HOURS_HOURS_9,
        hh.WorkingHoursEnum.HOURS_10: proto.WORKING_HOURS_HOURS_10,
        hh.WorkingHoursEnum.HOURS_11: proto.WORKING_HOURS_HOURS_11,
        hh.WorkingHoursEnum.HOURS_12: proto.WORKING_HOURS_HOURS_12,
        hh.WorkingHoursEnum.HOURS_24: proto.WORKING_HOURS_HOURS_24,
        hh.WorkingHoursEnum.FLEXIBLE: proto.WORKING_HOURS_FLEXIBLE,
        hh.WorkingHoursEnum.OTHER: proto.WORKING_HOURS_OTHER,
    }
    WORKING_HOURS_PYTHON: ClassVar[dict[proto.WorkingHours.ValueType, hh.WorkingHoursEnum]] = {
        proto.WORKING_HOURS_HOURS_2: hh.WorkingHoursEnum.HOURS_2,
        proto.WORKING_HOURS_HOURS_3: hh.WorkingHoursEnum.HOURS_3,
        proto.WORKING_HOURS_HOURS_4: hh.WorkingHoursEnum.HOURS_4,
        proto.WORKING_HOURS_HOURS_5: hh.WorkingHoursEnum.HOURS_5,
        proto.WORKING_HOURS_HOURS_6: hh.WorkingHoursEnum.HOURS_6,
        proto.WORKING_HOURS_HOURS_7: hh.WorkingHoursEnum.HOURS_7,
        proto.WORKING_HOURS_HOURS_8: hh.WorkingHoursEnum.HOURS_8,
        proto.WORKING_HOURS_HOURS_9: hh.WorkingHoursEnum.HOURS_9,
        proto.WORKING_HOURS_HOURS_10: hh.WorkingHoursEnum.HOURS_10,
        proto.WORKING_HOURS_HOURS_11: hh.WorkingHoursEnum.HOURS_11,
        proto.WORKING_HOURS_HOURS_12: hh.WorkingHoursEnum.HOURS_12,
        proto.WORKING_HOURS_HOURS_24: hh.WorkingHoursEnum.HOURS_24,
        proto.WORKING_HOURS_FLEXIBLE: hh.WorkingHoursEnum.FLEXIBLE,
        proto.WORKING_HOURS_OTHER: hh.WorkingHoursEnum.OTHER,
    }

    @classmethod
    def to_proto(cls, value: hh.WorkingHoursEnum) -> proto.WorkingHours.ValueType:
        return cls.WORKING_HOURS_PROTO.get(value, proto.WORKING_HOURS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.WorkingHours.ValueType) -> hh.WorkingHoursEnum | None:
        return cls.WORKING_HOURS_PYTHON.get(value, None)


@final
class FlyInFlyOutDurationMapper:
    FLY_IN_FLY_OUT_DURATION_PROTO: ClassVar[dict[hh.FlyInFlyOutDurationEnum, proto.FlyInFlyOutDuration.ValueType]] = {
        hh.FlyInFlyOutDurationEnum.DAYS_15: proto.FLY_IN_FLY_OUT_DURATION_DAYS_15,
        hh.FlyInFlyOutDurationEnum.DAYS_20: proto.FLY_IN_FLY_OUT_DURATION_DAYS_20,
        hh.FlyInFlyOutDurationEnum.DAYS_30: proto.FLY_IN_FLY_OUT_DURATION_DAYS_30,
        hh.FlyInFlyOutDurationEnum.DAYS_40: proto.FLY_IN_FLY_OUT_DURATION_DAYS_40,
        hh.FlyInFlyOutDurationEnum.DAYS_45: proto.FLY_IN_FLY_OUT_DURATION_DAYS_45,
        hh.FlyInFlyOutDurationEnum.DAYS_60: proto.FLY_IN_FLY_OUT_DURATION_DAYS_60,
        hh.FlyInFlyOutDurationEnum.DAYS_90: proto.FLY_IN_FLY_OUT_DURATION_DAYS_90,
        hh.FlyInFlyOutDurationEnum.DAYS_120: proto.FLY_IN_FLY_OUT_DURATION_DAYS_120,
        hh.FlyInFlyOutDurationEnum.DAYS_180: proto.FLY_IN_FLY_OUT_DURATION_DAYS_180,
        hh.FlyInFlyOutDurationEnum.OTHER: proto.FLY_IN_FLY_OUT_DURATION_OTHER,
    }
    FLY_IN_FLY_OUT_DURATION_PYTHON: ClassVar[dict[proto.FlyInFlyOutDuration.ValueType, hh.FlyInFlyOutDurationEnum]] = {
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_15: hh.FlyInFlyOutDurationEnum.DAYS_15,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_20: hh.FlyInFlyOutDurationEnum.DAYS_20,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_30: hh.FlyInFlyOutDurationEnum.DAYS_30,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_40: hh.FlyInFlyOutDurationEnum.DAYS_40,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_45: hh.FlyInFlyOutDurationEnum.DAYS_45,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_60: hh.FlyInFlyOutDurationEnum.DAYS_60,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_90: hh.FlyInFlyOutDurationEnum.DAYS_90,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_120: hh.FlyInFlyOutDurationEnum.DAYS_120,
        proto.FLY_IN_FLY_OUT_DURATION_DAYS_180: hh.FlyInFlyOutDurationEnum.DAYS_180,
        proto.FLY_IN_FLY_OUT_DURATION_OTHER: hh.FlyInFlyOutDurationEnum.OTHER,
    }

    @classmethod
    def to_proto(cls, value: hh.FlyInFlyOutDurationEnum) -> proto.FlyInFlyOutDuration.ValueType:
        return cls.FLY_IN_FLY_OUT_DURATION_PROTO.get(value, proto.FLY_IN_FLY_OUT_DURATION_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.FlyInFlyOutDuration.ValueType) -> hh.FlyInFlyOutDurationEnum | None:
        return cls.FLY_IN_FLY_OUT_DURATION_PYTHON.get(value, None)


@final
class WorkScheduleByDaysMapper:
    WORK_SCHEDULE_BY_DAYS_PROTO: ClassVar[dict[hh.WorkScheduleByDaysEnum, proto.WorkScheduleByDays.ValueType]] = {
        hh.WorkScheduleByDaysEnum.SIX_ON_ONE_OFF: proto.WORK_SCHEDULE_BY_DAYS_SIX_ON_ONE_OFF,
        hh.WorkScheduleByDaysEnum.FIVE_ON_TWO_OFF: proto.WORK_SCHEDULE_BY_DAYS_FIVE_ON_TWO_OFF,
        hh.WorkScheduleByDaysEnum.FOUR_ON_FOUR_OFF: proto.WORK_SCHEDULE_BY_DAYS_FOUR_ON_FOUR_OFF,
        hh.WorkScheduleByDaysEnum.FOUR_ON_THREE_OFF: proto.WORK_SCHEDULE_BY_DAYS_FOUR_ON_THREE_OFF,
        hh.WorkScheduleByDaysEnum.FOUR_ON_TWO_OFF: proto.WORK_SCHEDULE_BY_DAYS_FOUR_ON_TWO_OFF,
        hh.WorkScheduleByDaysEnum.THREE_ON_THREE_OFF: proto.WORK_SCHEDULE_BY_DAYS_THREE_ON_THREE_OFF,
        hh.WorkScheduleByDaysEnum.THREE_ON_TWO_OFF: proto.WORK_SCHEDULE_BY_DAYS_THREE_ON_TWO_OFF,
        hh.WorkScheduleByDaysEnum.TWO_ON_TWO_OFF: proto.WORK_SCHEDULE_BY_DAYS_TWO_ON_TWO_OFF,
        hh.WorkScheduleByDaysEnum.TWO_ON_ONE_OFF: proto.WORK_SCHEDULE_BY_DAYS_TWO_ON_ONE_OFF,
        hh.WorkScheduleByDaysEnum.ONE_ON_THREE_OFF: proto.WORK_SCHEDULE_BY_DAYS_ONE_ON_THREE_OFF,
        hh.WorkScheduleByDaysEnum.ONE_ON_TWO_OFF: proto.WORK_SCHEDULE_BY_DAYS_ONE_ON_TWO_OFF,
        hh.WorkScheduleByDaysEnum.WEEKEND: proto.WORK_SCHEDULE_BY_DAYS_WEEKEND,
        hh.WorkScheduleByDaysEnum.FLEXIBLE: proto.WORK_SCHEDULE_BY_DAYS_FLEXIBLE,
        hh.WorkScheduleByDaysEnum.OTHER: proto.WORK_SCHEDULE_BY_DAYS_OTHER,
    }
    WORK_SCHEDULE_BY_DAYS_PYTHON: ClassVar[dict[proto.WorkScheduleByDays.ValueType, hh.WorkScheduleByDaysEnum]] = {
        proto.WORK_SCHEDULE_BY_DAYS_SIX_ON_ONE_OFF: hh.WorkScheduleByDaysEnum.SIX_ON_ONE_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_FIVE_ON_TWO_OFF: hh.WorkScheduleByDaysEnum.FIVE_ON_TWO_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_FOUR_ON_FOUR_OFF: hh.WorkScheduleByDaysEnum.FOUR_ON_FOUR_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_FOUR_ON_THREE_OFF: hh.WorkScheduleByDaysEnum.FOUR_ON_THREE_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_FOUR_ON_TWO_OFF: hh.WorkScheduleByDaysEnum.FOUR_ON_TWO_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_THREE_ON_THREE_OFF: hh.WorkScheduleByDaysEnum.THREE_ON_THREE_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_THREE_ON_TWO_OFF: hh.WorkScheduleByDaysEnum.THREE_ON_TWO_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_TWO_ON_TWO_OFF: hh.WorkScheduleByDaysEnum.TWO_ON_TWO_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_TWO_ON_ONE_OFF: hh.WorkScheduleByDaysEnum.TWO_ON_ONE_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_ONE_ON_THREE_OFF: hh.WorkScheduleByDaysEnum.ONE_ON_THREE_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_ONE_ON_TWO_OFF: hh.WorkScheduleByDaysEnum.ONE_ON_TWO_OFF,
        proto.WORK_SCHEDULE_BY_DAYS_WEEKEND: hh.WorkScheduleByDaysEnum.WEEKEND,
        proto.WORK_SCHEDULE_BY_DAYS_FLEXIBLE: hh.WorkScheduleByDaysEnum.FLEXIBLE,
        proto.WORK_SCHEDULE_BY_DAYS_OTHER: hh.WorkScheduleByDaysEnum.OTHER,
    }

    @classmethod
    def to_proto(cls, value: hh.WorkScheduleByDaysEnum) -> proto.WorkScheduleByDays.ValueType:
        return cls.WORK_SCHEDULE_BY_DAYS_PROTO.get(value, proto.WORK_SCHEDULE_BY_DAYS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.WorkScheduleByDays.ValueType) -> hh.WorkScheduleByDaysEnum | None:
        return cls.WORK_SCHEDULE_BY_DAYS_PYTHON.get(value, None)


@final
class SalaryRangeModeMapper:
    SALARY_RANGE_MODE_PROTO: ClassVar[dict[hh.SalaryRangeModeEnum, proto.SalaryRangeMode.ValueType]] = {
        hh.SalaryRangeModeEnum.MONTH: proto.SALARY_RANGE_MODE_MONTH,
        hh.SalaryRangeModeEnum.SHIFT: proto.SALARY_RANGE_MODE_SHIFT,
        hh.SalaryRangeModeEnum.HOUR: proto.SALARY_RANGE_MODE_HOUR,
        hh.SalaryRangeModeEnum.FLY_IN_FLY_OUT: proto.SALARY_RANGE_MODE_FLY_IN_FLY_OUT,
        hh.SalaryRangeModeEnum.SERVICE: proto.SALARY_RANGE_MODE_SERVICE,
    }
    SALARY_RANGE_MODE_PYTHON: ClassVar[dict[proto.SalaryRangeMode.ValueType, hh.SalaryRangeModeEnum]] = {
        proto.SALARY_RANGE_MODE_MONTH: hh.SalaryRangeModeEnum.MONTH,
        proto.SALARY_RANGE_MODE_SHIFT: hh.SalaryRangeModeEnum.SHIFT,
        proto.SALARY_RANGE_MODE_HOUR: hh.SalaryRangeModeEnum.HOUR,
        proto.SALARY_RANGE_MODE_FLY_IN_FLY_OUT: hh.SalaryRangeModeEnum.FLY_IN_FLY_OUT,
        proto.SALARY_RANGE_MODE_SERVICE: hh.SalaryRangeModeEnum.SERVICE,
    }

    @classmethod
    def to_proto(cls, value: hh.SalaryRangeModeEnum) -> proto.SalaryRangeMode.ValueType:
        return cls.SALARY_RANGE_MODE_PROTO.get(value, proto.SALARY_RANGE_MODE_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.SalaryRangeMode.ValueType) -> hh.SalaryRangeModeEnum | None:
        return cls.SALARY_RANGE_MODE_PYTHON.get(value, None)


@final
class SalaryRangeFrequencyMapper:
    SALARY_RANGE_FREQUENCY_PROTO: ClassVar[dict[hh.SalaryRangeFrequencyEnum, proto.SalaryRangeFrequency.ValueType]] = {
        hh.SalaryRangeFrequencyEnum.DAILY: proto.SALARY_RANGE_FREQUENCY_DAILY,
        hh.SalaryRangeFrequencyEnum.WEEKLY: proto.SALARY_RANGE_FREQUENCY_WEEKLY,
        hh.SalaryRangeFrequencyEnum.TWICE_PER_MONTH: proto.SALARY_RANGE_FREQUENCY_TWICE_PER_MONTH,
        hh.SalaryRangeFrequencyEnum.MONTHLY: proto.SALARY_RANGE_FREQUENCY_MONTHLY,
        hh.SalaryRangeFrequencyEnum.PER_PROJECT: proto.SALARY_RANGE_FREQUENCY_PER_PROJECT,
    }
    SALARY_RANGE_FREQUENCY_PYTHON: ClassVar[dict[proto.SalaryRangeFrequency.ValueType, hh.SalaryRangeFrequencyEnum]] = {
        proto.SALARY_RANGE_FREQUENCY_DAILY: hh.SalaryRangeFrequencyEnum.DAILY,
        proto.SALARY_RANGE_FREQUENCY_WEEKLY: hh.SalaryRangeFrequencyEnum.WEEKLY,
        proto.SALARY_RANGE_FREQUENCY_TWICE_PER_MONTH: hh.SalaryRangeFrequencyEnum.TWICE_PER_MONTH,
        proto.SALARY_RANGE_FREQUENCY_MONTHLY: hh.SalaryRangeFrequencyEnum.MONTHLY,
        proto.SALARY_RANGE_FREQUENCY_PER_PROJECT: hh.SalaryRangeFrequencyEnum.PER_PROJECT,
    }

    @classmethod
    def to_proto(cls, value: hh.SalaryRangeFrequencyEnum) -> proto.SalaryRangeFrequency.ValueType:
        return cls.SALARY_RANGE_FREQUENCY_PROTO.get(value, proto.SALARY_RANGE_FREQUENCY_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.SalaryRangeFrequency.ValueType) -> hh.SalaryRangeFrequencyEnum | None:
        return cls.SALARY_RANGE_FREQUENCY_PYTHON.get(value, None)


@final
class AgeRestrictionMapper:
    AGE_RESTRICTION_PROTO: ClassVar[dict[hh.AgeRestrictionEnum, proto.AgeRestriction.ValueType]] = {
        hh.AgeRestrictionEnum.AGE_14_PLUS: proto.AGE_RESTRICTION_AGE_14_PLUS,
        hh.AgeRestrictionEnum.AGE_16_PLUS: proto.AGE_RESTRICTION_AGE_16_PLUS,
    }
    AGE_RESTRICTION_PYTHON: ClassVar[dict[proto.AgeRestriction.ValueType, hh.AgeRestrictionEnum]] = {
        proto.AGE_RESTRICTION_AGE_14_PLUS: hh.AgeRestrictionEnum.AGE_14_PLUS,
        proto.AGE_RESTRICTION_AGE_16_PLUS: hh.AgeRestrictionEnum.AGE_16_PLUS,
    }

    @classmethod
    def to_proto(cls, value: hh.AgeRestrictionEnum) -> proto.AgeRestriction.ValueType:
        return cls.AGE_RESTRICTION_PROTO.get(value, proto.AGE_RESTRICTION_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.AgeRestriction.ValueType) -> hh.AgeRestrictionEnum | None:
        return cls.AGE_RESTRICTION_PYTHON.get(value, None)


@final
class CivilLawContractsMapper:
    CIVIL_LAW_CONTRACTS_PROTO: ClassVar[dict[hh.CivilLawContractsEnum, proto.CivilLawContracts.ValueType]] = {
        hh.CivilLawContractsEnum.SELF_EMPLOYED: proto.CIVIL_LAW_CONTRACTS_SELF_EMPLOYED,
        hh.CivilLawContractsEnum.INDIVIDUAL_ENTREPRENEUR: proto.CIVIL_LAW_CONTRACTS_INDIVIDUAL_ENTREPRENEUR,
        hh.CivilLawContractsEnum.INDIVIDUAL_PERSON: proto.CIVIL_LAW_CONTRACTS_INDIVIDUAL_PERSON,
    }
    CIVIL_LAW_CONTRACTS_PYTHON: ClassVar[dict[proto.CivilLawContracts.ValueType, hh.CivilLawContractsEnum]] = {
        proto.CIVIL_LAW_CONTRACTS_SELF_EMPLOYED: hh.CivilLawContractsEnum.SELF_EMPLOYED,
        proto.CIVIL_LAW_CONTRACTS_INDIVIDUAL_ENTREPRENEUR: hh.CivilLawContractsEnum.INDIVIDUAL_ENTREPRENEUR,
        proto.CIVIL_LAW_CONTRACTS_INDIVIDUAL_PERSON: hh.CivilLawContractsEnum.INDIVIDUAL_PERSON,
    }

    @classmethod
    def to_proto(cls, value: hh.CivilLawContractsEnum) -> proto.CivilLawContracts.ValueType:
        return cls.CIVIL_LAW_CONTRACTS_PROTO.get(value, proto.CIVIL_LAW_CONTRACTS_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.CivilLawContracts.ValueType) -> hh.CivilLawContractsEnum | None:
        return cls.CIVIL_LAW_CONTRACTS_PYTHON.get(value, None)


@final
class ResumeSearchLabelMapper:
    RESUME_SEARCH_LABEL_PROTO: ClassVar[dict[hh.ResumeSearchLabelEnum, proto.ResumeSearchLabel.ValueType]] = {
        hh.ResumeSearchLabelEnum.ONLY_WITH_PHOTO: proto.RESUME_SEARCH_LABEL_ONLY_WITH_PHOTO,
        hh.ResumeSearchLabelEnum.ONLY_WITH_SALARY: proto.RESUME_SEARCH_LABEL_ONLY_WITH_SALARY,
        hh.ResumeSearchLabelEnum.ONLY_WITH_AGE: proto.RESUME_SEARCH_LABEL_ONLY_WITH_AGE,
        hh.ResumeSearchLabelEnum.ONLY_WITH_GENDER: proto.RESUME_SEARCH_LABEL_ONLY_WITH_GENDER,
        hh.ResumeSearchLabelEnum.ONLY_WITH_VEHICLE: proto.RESUME_SEARCH_LABEL_ONLY_WITH_VEHICLE,
        hh.ResumeSearchLabelEnum.EXCLUDE_VIEWED_BY_USER_ID: proto.RESUME_SEARCH_LABEL_EXCLUDE_VIEWED_BY_USER_ID,
        hh.ResumeSearchLabelEnum.EXCLUDE_VIEWED_BY_EMPLOYER_ID: proto.RESUME_SEARCH_LABEL_EXCLUDE_VIEWED_BY_EMPLOYER_ID,
        hh.ResumeSearchLabelEnum.ONLY_IN_RESPONSES: proto.RESUME_SEARCH_LABEL_ONLY_IN_RESPONSES,
    }
    RESUME_SEARCH_LABEL_PYTHON: ClassVar[dict[proto.ResumeSearchLabel.ValueType, hh.ResumeSearchLabelEnum]] = {
        proto.RESUME_SEARCH_LABEL_ONLY_WITH_PHOTO: hh.ResumeSearchLabelEnum.ONLY_WITH_PHOTO,
        proto.RESUME_SEARCH_LABEL_ONLY_WITH_SALARY: hh.ResumeSearchLabelEnum.ONLY_WITH_SALARY,
        proto.RESUME_SEARCH_LABEL_ONLY_WITH_AGE: hh.ResumeSearchLabelEnum.ONLY_WITH_AGE,
        proto.RESUME_SEARCH_LABEL_ONLY_WITH_GENDER: hh.ResumeSearchLabelEnum.ONLY_WITH_GENDER,
        proto.RESUME_SEARCH_LABEL_ONLY_WITH_VEHICLE: hh.ResumeSearchLabelEnum.ONLY_WITH_VEHICLE,
        proto.RESUME_SEARCH_LABEL_EXCLUDE_VIEWED_BY_USER_ID: hh.ResumeSearchLabelEnum.EXCLUDE_VIEWED_BY_USER_ID,
        proto.RESUME_SEARCH_LABEL_EXCLUDE_VIEWED_BY_EMPLOYER_ID: hh.ResumeSearchLabelEnum.EXCLUDE_VIEWED_BY_EMPLOYER_ID,
        proto.RESUME_SEARCH_LABEL_ONLY_IN_RESPONSES: hh.ResumeSearchLabelEnum.ONLY_IN_RESPONSES,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeSearchLabelEnum) -> proto.ResumeSearchLabel.ValueType:
        return cls.RESUME_SEARCH_LABEL_PROTO.get(value, proto.RESUME_SEARCH_LABEL_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeSearchLabel.ValueType) -> hh.ResumeSearchLabelEnum | None:
        return cls.RESUME_SEARCH_LABEL_PYTHON.get(value, None)


@final
class ResumeSearchRelocationMapper:
    RESUME_SEARCH_RELOCATION_PROTO: ClassVar[
        dict[hh.ResumeSearchRelocationEnum, proto.ResumeSearchRelocation.ValueType]
    ] = {
        hh.ResumeSearchRelocationEnum.LIVING_OR_RELOCATION: proto.RESUME_SEARCH_RELOCATION_LIVING_OR_RELOCATION,
        hh.ResumeSearchRelocationEnum.LIVING: proto.RESUME_SEARCH_RELOCATION_LIVING,
        hh.ResumeSearchRelocationEnum.LIVING_BUT_RELOCATION: proto.RESUME_SEARCH_RELOCATION_LIVING_BUT_RELOCATION,
        hh.ResumeSearchRelocationEnum.RELOCATION: proto.RESUME_SEARCH_RELOCATION_RELOCATION,
    }
    RESUME_SEARCH_RELOCATION_PYTHON: ClassVar[
        dict[proto.ResumeSearchRelocation.ValueType, hh.ResumeSearchRelocationEnum]
    ] = {
        proto.RESUME_SEARCH_RELOCATION_LIVING_OR_RELOCATION: hh.ResumeSearchRelocationEnum.LIVING_OR_RELOCATION,
        proto.RESUME_SEARCH_RELOCATION_LIVING: hh.ResumeSearchRelocationEnum.LIVING,
        proto.RESUME_SEARCH_RELOCATION_LIVING_BUT_RELOCATION: hh.ResumeSearchRelocationEnum.LIVING_BUT_RELOCATION,
        proto.RESUME_SEARCH_RELOCATION_RELOCATION: hh.ResumeSearchRelocationEnum.RELOCATION,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeSearchRelocationEnum) -> proto.ResumeSearchRelocation.ValueType:
        return cls.RESUME_SEARCH_RELOCATION_PROTO.get(value, proto.RESUME_SEARCH_RELOCATION_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeSearchRelocation.ValueType) -> hh.ResumeSearchRelocationEnum | None:
        return cls.RESUME_SEARCH_RELOCATION_PYTHON.get(value, None)


@final
class ResumeSearchOrderMapper:
    RESUME_SEARCH_ORDER_PROTO: ClassVar[dict[hh.ResumeSearchOrderEnum, proto.ResumeSearchOrder.ValueType]] = {
        hh.ResumeSearchOrderEnum.PUBLICATION_TIME: proto.RESUME_SEARCH_ORDER_PUBLICATION_TIME,
        hh.ResumeSearchOrderEnum.SALARY_DESC: proto.RESUME_SEARCH_ORDER_SALARY_DESC,
        hh.ResumeSearchOrderEnum.SALARY_ASC: proto.RESUME_SEARCH_ORDER_SALARY_ASC,
        hh.ResumeSearchOrderEnum.RELEVANCE: proto.RESUME_SEARCH_ORDER_RELEVANCE,
    }
    RESUME_SEARCH_ORDER_PYTHON: ClassVar[dict[proto.ResumeSearchOrder.ValueType, hh.ResumeSearchOrderEnum]] = {
        proto.RESUME_SEARCH_ORDER_PUBLICATION_TIME: hh.ResumeSearchOrderEnum.PUBLICATION_TIME,
        proto.RESUME_SEARCH_ORDER_SALARY_DESC: hh.ResumeSearchOrderEnum.SALARY_DESC,
        proto.RESUME_SEARCH_ORDER_SALARY_ASC: hh.ResumeSearchOrderEnum.SALARY_ASC,
        proto.RESUME_SEARCH_ORDER_RELEVANCE: hh.ResumeSearchOrderEnum.RELEVANCE,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeSearchOrderEnum) -> proto.ResumeSearchOrder.ValueType:
        return cls.RESUME_SEARCH_ORDER_PROTO.get(value, proto.RESUME_SEARCH_ORDER_UNSPECIFIED)

    @classmethod
    def to_python(cls, value: proto.ResumeSearchOrder.ValueType) -> hh.ResumeSearchOrderEnum | None:
        return cls.RESUME_SEARCH_ORDER_PYTHON.get(value, None)


@final
class ResumeSearchExperiencePeriodMapper:
    RESUME_SEARCH_EXPERIENCE_PERIOD_PROTO: ClassVar[
        dict[hh.ResumeSearchExperiencePeriodEnum, proto.ResumeSearchExperiencePeriod.ValueType]
    ] = {
        hh.ResumeSearchExperiencePeriodEnum.ALL_TIME: proto.RESUME_SEARCH_EXPERIENCE_PERIOD_ALL_TIME,
        hh.ResumeSearchExperiencePeriodEnum.LAST_YEAR: proto.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_YEAR,
        hh.ResumeSearchExperiencePeriodEnum.LAST_THREE_YEARS: proto.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_THREE_YEARS,
        hh.ResumeSearchExperiencePeriodEnum.LAST_SIX_YEARS: proto.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_SIX_YEARS,
    }
    RESUME_SEARCH_EXPERIENCE_PERIOD_PYTHON: ClassVar[
        dict[proto.ResumeSearchExperiencePeriod.ValueType, hh.ResumeSearchExperiencePeriodEnum]
    ] = {
        proto.RESUME_SEARCH_EXPERIENCE_PERIOD_ALL_TIME: hh.ResumeSearchExperiencePeriodEnum.ALL_TIME,
        proto.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_YEAR: hh.ResumeSearchExperiencePeriodEnum.LAST_YEAR,
        proto.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_THREE_YEARS: hh.ResumeSearchExperiencePeriodEnum.LAST_THREE_YEARS,
        proto.RESUME_SEARCH_EXPERIENCE_PERIOD_LAST_SIX_YEARS: hh.ResumeSearchExperiencePeriodEnum.LAST_SIX_YEARS,
    }

    @classmethod
    def to_proto(cls, value: hh.ResumeSearchExperiencePeriodEnum) -> proto.ResumeSearchExperiencePeriod.ValueType:
        return cls.RESUME_SEARCH_EXPERIENCE_PERIOD_PROTO.get(value, proto.RESUME_SEARCH_EXPERIENCE_PERIOD_UNSPECIFIED)

    @classmethod
    def to_python(
        cls, value: proto.ResumeSearchExperiencePeriod.ValueType
    ) -> hh.ResumeSearchExperiencePeriodEnum | None:
        return cls.RESUME_SEARCH_EXPERIENCE_PERIOD_PYTHON.get(value, None)
