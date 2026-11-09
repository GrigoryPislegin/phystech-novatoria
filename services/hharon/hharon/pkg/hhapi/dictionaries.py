from enum import StrEnum


class ResumeAccessTypeEnum(StrEnum):
    NO_ONE = "no_one"
    """ Не видно никому """
    WHITELIST = "whitelist"
    """ Видно выбранным работодателям """
    BLACKLIST = "blacklist"
    """ Скрыто от выбранных работодателей """
    CLIENTS = "clients"
    """ Видно всем работодателям, зарегистрированным на hh.ru """
    EVERYONE = "everyone"
    """ видно всему интернету """
    DIRECT = "direct"
    """ доступно только по прямой ссылке """


class VacancySearchOrderEnum(StrEnum):
    PUBLICATION_TIME = "publication_time"
    """ по дате """
    SALARY_DESC = "salary_desc"
    """ по убыванию дохода """
    SALARY_ASC = "salary_asc"
    """ по возрастанию дохода """
    RELEVANCE = "relevance"
    """ по соответствию """
    DISTANCE = "distance"
    """ по удалённости """


class VacancySearchFieldsEnum(StrEnum):
    NAME = "name"
    """ в названии вакансии """
    COMPANY_NAME = "company_name"
    """ в названии компании """
    DESCRIPTION = "description"
    """ в описании вакансии """


class VacancySearchEmploymentFormEnum(StrEnum):
    FULL = "FULL"
    """ Полная занятость """
    PART = "PART"
    """ Частичная занятость """
    PROJECT = "PROJECT"
    """ Подработка """
    FLY_IN_FLY_OUT = "FLY_IN_FLY_OUT"
    """ Вахта """


class GenderEnum(StrEnum):
    MALE = "male"
    """ Мужской """
    FEMALE = "female"
    """ Женский """


class PreferredContactTypeEnum(StrEnum):
    HOME = "home"
    """ Домашний телефон """
    WORK = "work"
    """ Рабочий телефон """
    CELL = "cell"
    """ Мобильный телефон """
    EMAIL = "email"
    """ Эл. почта """


class TravelTimeEnum(StrEnum):
    ANY = "any"
    """ Не имеет значения """
    LESS_THAN_HOUR = "less_than_hour"
    """ Не более часа """
    FROM_HOUR_TO_ONE_AND_HALF = "from_hour_to_one_and_half"
    """ Не более полутора часов """


class RelocationTypeEnum(StrEnum):
    NO_RELOCATION = "no_relocation"
    """ не могу переехать """
    RELOCATION_POSSIBLE = "relocation_possible"
    """ могу переехать """
    RELOCATION_DESIRABLE = "relocation_desirable"
    """ хочу переехать """


class BusinessTripReadinessEnum(StrEnum):
    READY = "ready"
    """ Готов к командировкам """
    SOMETIMES = "sometimes"
    """ Готов к редким командировкам """
    NEVER = "never"
    """ Не готов к командировкам """


class ResumeContactsSiteTypeEnum(StrEnum):
    PERSONAL = "personal"
    """ Другой сайт """
    MOI_KRUG = "moi_krug"
    """ Мой круг """
    LIVEJOURNAL = "livejournal"
    """ LiveJournal """
    LINKEDIN = "linkedin"
    """ LinkedIn """
    FREELANCE = "freelance"
    """ Free-lance """
    SKYPE = "skype"
    """ Skype """


class EmployerTypeEnum(StrEnum):
    COMPANY = "company"
    """ Организация """
    AGENCY = "agency"
    """ Кадровое агентство """
    PROJECT_DIRECTOR = "project_director"
    """ Проект """
    PRIVATE_RECRUITER = "private_recruiter"
    """ Частный рекрутер """
    PRIVATE_INDIVIDUAL = "private_individual"
    """ Частное лицо """
    SELF_EMPLOYED = "self_employed"
    """ Самозанятый """


class EmployerRelationEnum(StrEnum):
    BLACKLISTED = "blacklisted"
    """ Скрыт из поиска вакансий """


class NegotiationsStateEnum(StrEnum):
    RESPONSE = "response"
    """ Отклик """
    INVITATION = "invitation"
    """ Приглашение """
    DISCARD = "discard"
    """ Отказ """
    HIDDEN = "hidden"
    """ Скрытый """
    INTERVIEW = "interview"
    """ Собеседование """
    HIRED = "hired"
    """ Выход на работу """


class ApplicantNegotiationStatusEnum(StrEnum):
    ALL = "all"
    """ Все """
    ACTIVE = "active"
    """ Активные """
    INVITATIONS = "invitations"
    """ Активные приглашения """
    RESPONSE = "response"
    """ Активные отклики """
    DISCARD = "discard"
    """ Отказ """
    ARCHIVED = "archived"
    """ Архивированные """
    NON_ARCHIVED = "non_archived"
    """ Все, кроме архивированных """
    DELETED = "deleted"
    """ Скрытые """
    INTERVIEW = "interview"
    """ Собеседование """
    HIRED = "hired"
    """ Выход на работу """


class NegotiationsParticipantTypeEnum(StrEnum):
    APPLICANT = "applicant"
    """ Соискатель """
    EMPLOYER = "employer"
    """ Работодатель """


class NegotiationsOrderEnum(StrEnum):
    UPDATED_AT = "updated_at"
    """ по дате обновления """
    CREATED_AT = "created_at"
    """ по дате добавления """


class ResumeModerationNoteEnum(StrEnum):
    BAD = "bad"
    """ Резюме составлено небрежно. """
    BLOCK_FULL_NAME = "block_full_name"
    """ В резюме отсутствует полное имя кандидата. """
    BAD_DESCRIPTION = "bad_description"
    """ Укажите желаемую позицию, чтобы повысить свои шансы найти работу. """
    BLOCK_NO_EDUCATION_PLACE_OR_DATE = "block_no_education_place_or_date"
    """ Отсутствуют данные об учебном заведении и дате его окончания. """
    BAD_EDUCATION = "bad_education"
    """ Плохо описано образование. """
    BAD_EDUCATION_STUDENT = "bad_education_student"
    """ Укажите полное название учебного заведения, факультет и планируемый год окончания. """
    BLOCK_NO_FUNCTION = "block_no_function"
    """ Опишите подробнее свои обязанности и функции. """
    BLOCK_WORK_PLACE = "block_work_place"
    """ Не указан опыт работы за последнее время """
    NO_COMPANY_NAME = "no_company_name"
    """ Укажите названия мест работы. """
    NO_COMPANY_DESCRIPTION = "no_company_description"
    """ Укажите сферу деятельности компаний, в которых Вы работали. """
    NO_POSITION = "no_position"
    """ Плохо описаны занимаемые должности. """
    NO_DATE = "no_date"
    """ Отсутствуют даты начала и окончания работы. """
    BAD_FUNCTION = "bad_function"
    """ Плохо описаны функции и обязанности. """
    NOT_ENOUGH_INFORMATION = "not_enough_information"
    """ Укажите больше дополнительной информации: владение иностранными языками, знание компьютерных программ и др. """
    LOT_INFORMATION = "lot_information"
    """ Слишком много дополнительной информации. """
    NO_RECOMMENDATION = "no_recommendation"
    """ Вы не предоставили ни одну рекомендацию. """
    CARELESS_ADDITIONAL_INFORMATION = "careless_additional_information"
    """ Обратите внимание на раздел «Ключевые навыки». Укажите в нём сведения, которые выгодно отличат Вас в качестве претендента на желаемую позицию. Проверьте орфографию и опечатки. """
    CARELESS_PHOTO = "careless_photo"
    """ Рекомендуем Вам изменить фотографию для резюме. Лучше размещать фотографии, где Вы изображены в деловом или повседневном костюме. """
    CARELESS_KEY_SKILL_INFORMATION = "careless_key_skill_information"
    """ Отредактируйте раздел «Ключевые навыки» Вашего резюме, поскольку указанная информация не вполне соответствует формату и/или содержит опечатки. """
    INCORRECT_PHONE_NUMBER = "incorrect_phone_number"
    """ В резюме указан несуществующий номер телефона. Если номер корректен, свяжитесь со службой поддержки """
    BLOCK_OBSCENITY = "block_obscenity"
    """ Мат в резюме """
    BLOCK_OBSCENITY_NAME = "block_obscenity_name"
    """ Мат в ФИО """
    BLOCK_OBSCENITY_TITLE = "block_obscenity_title"
    """ Мат в названии должности """
    BLOCK_OBSCENITY_EXPERIENCE = "block_obscenity_experience"
    """ Мат в разделе "Опыт работы" """
    BLOCK_OBSCENITY_SKILLS = "block_obscenity_skills"
    """ Мат в поле "О себе" """
    BLOCK_OBSCENITY_KEY_SKILLS = "block_obscenity_key_skills"
    """ Мат в ключевых навыках """
    BLOCK_OBSCENITY_EDUCATION = "block_obscenity_education"
    """ Мат в разделе "Образование" """
    BLOCK_OBSCENITY_ADDITIONAL_EDUCATION = "block_obscenity_additional_education"
    """ Мат в разделе "Повышение квалификации и курсы" """
    BLOCK_OBSCENITY_ATTESTATION_EDUCATION = "block_obscenity_attestation_education"
    """ Мат в разделе "Тесты и экзамены" """
    BLOCK_OBSCENITY_ELEMENTARY_EDUCATION = "block_obscenity_elementary_education"
    """ Мат в разделе "Начальное образование" """
    BLOCK_OBSCENITY_RECOMMENDATION = "block_obscenity_recommendation"
    """ Мат в разделе "Рекомендации" """
    BLOCK_EXPERIENCE_IN_ONE_PLACE = "block_experience_in_one_place"
    """ Укажите опыт отдельно для каждой компании """
    EXPERIENCE_CAPS = "experience_caps"
    """ При описании опыта работы проследите, что ЗАГЛАВНЫЕ БУКВЫ использованы только в начале предложений или для имен собственных """
    EXPERIENCE_MULTILANG = "experience_multilang"
    """ Опыт работы должен быть описан на одном языке """
    EXPERIENCE_SPELLING = "experience_spelling"
    """ Исправьте орфографические ошибки в описании опыта работы """
    BLOCK_EXPERIENCE_IN_ADDITIONAL_INFORMATION = "block_experience_in_additional_information"
    """ Опишите опыт работы в соответствующих полях """
    ADDITIONAL_INFORMATION_CAPS = "additional_information_caps"
    """ При заполнении поля "О себе" проследите, что ЗАГЛАВНЫЕ БУКВЫ использованы только в начале предложений или для имен собственных """
    ADDITIONAL_INFORMATION_MULTILANG = "additional_information_multilang"
    """ Поле "О себе" должно быть написано на одном языке """
    ADDITIONAL_INFORMATION_SPELLING = "additional_information_spelling"
    """ Исправьте орфографические ошибки в поле "О себе" """


class VacancyRelationEnum(StrEnum):
    FAVORITED = "favorited"
    """ В избранном """
    GOT_RESPONSE = "got_response"
    """ Вы отправили резюме """
    GOT_INVITATION = "got_invitation"
    """ Вас пригласили """
    GOT_REJECTION = "got_rejection"
    """ Вам отказали """
    BLACKLISTED = "blacklisted"
    """ Скрыта из поиска """
    GOT_QUESTION = "got_question"
    """ Вы задали вопрос по вакансии """


class ResumeStatusEnum(StrEnum):
    NOT_PUBLISHED = "not_published"
    """ не опубликовано """
    PUBLISHED = "published"
    """ опубликовано """
    BLOCKED = "blocked"
    """ заблокирован """
    ON_MODERATION = "on_moderation"
    """ на модерации """


class ResumeSearchLogicEnum(StrEnum):
    ALL = "all"
    """ Все слова встречаются """
    ANY = "any"
    """ Любое из слов встречается """
    PHRASE = "phrase"
    """ Точная фраза встречается """
    EXCEPT = "except"
    """ Не встречаются """


class ResumeSearchFieldsEnum(StrEnum):
    EVERYWHERE = "everywhere"
    """ везде """
    TITLE = "title"
    """ в названии резюме """
    EDUCATION = "education"
    """ в образовании """
    SKILLS = "skills"
    """ в ключевых навыках """
    EXPERIENCE = "experience"
    """ в опыте работы """
    EXPERIENCE_COMPANY = "experience_company"
    """ в компаниях и отраслях """
    EXPERIENCE_POSITION = "experience_position"
    """ в должностях """
    EXPERIENCE_DESCRIPTION = "experience_description"
    """ в обязанностях """


class MessagingStatusEnum(StrEnum):
    ARCHIVED = "archived"
    """ Вакансия отправлена в архив """
    OK = "ok"
    """ Переписка доступна """
    DISABLED_BY_EMPLOYER = "disabled_by_employer"
    """ Работодатель отключил переписку """
    IN_A_ROW_LIMIT = "in_a_row_limit"
    """ Вы отправили 5 сообщений подряд. Дождитесь ответа, чтобы написать еще """
    OVERALL_LIMIT = "overall_limit"
    """ Превышено число сообщений в переписке """
    NO_INVITATION = "no_invitation"
    """ Переписка доступна только после приглашения """
    RESUME_DELETED = "resume_deleted"
    """ Резюме удалено """
    PROHIBITED = "prohibited"
    """ Переписка недоступна """


class EmployerActiveVacanciesOrderEnum(StrEnum):
    NAME_ASC = "name_asc"
    """ по заголовку """
    NAME_DESC = "name_desc"
    """ по заголовку, в обратном порядке """
    EXPIRATION_DATE_ASC = "expiration_date_asc"
    """ по дате """
    EXPIRATION_DATE_DESC = "expiration_date_desc"
    """ по убыванию даты """
    UNSEEN_RESPONSES_ASC = "unseen_responses_asc"
    """ по возрастанию количества непросмотренных откликов """
    UNSEEN_RESPONSES_DESC = "unseen_responses_desc"
    """ по убыванию количества непросмотренных откликов """


class EmployerArchivedVacanciesOrderEnum(StrEnum):
    NAME_ASC = "name_asc"
    """ по заголовку """
    NAME_DESC = "name_desc"
    """ по заголовку, в обратном порядке """
    ARCHIVE_TIME_ASC = "archive_time_asc"
    """ по дате архивации """
    ARCHIVE_TIME_DESC = "archive_time_desc"
    """ по убыванию даты архивации """


class EmployerHiddenVacanciesOrderEnum(StrEnum):
    NAME_ASC = "name_asc"
    """ по заголовку """
    NAME_DESC = "name_desc"
    """ по заголовку, в обратном порядке """
    ARCHIVE_TIME_ASC = "archive_time_asc"
    """ по дате архивации """
    ARCHIVE_TIME_DESC = "archive_time_desc"
    """ по убыванию даты архивации """


class ApplicantCommentsOrderEnum(StrEnum):
    CREATION_TIME_DESC = "creation_time_desc"
    """ по убыванию даты публикации """
    CREATION_TIME_ASC = "creation_time_asc"
    """ по дате публикации """


class VacancyNotProlongedReasonEnum(StrEnum):
    VACANCY_ARCHIVED = "vacancy_archived"
    """ Нельзя поднять архивную или заблокированную вакансию """
    VACANCY_NOT_PREMODERATED = "vacancy_not_premoderated"
    """ Вакансия не прошла модерацию """
    PFP_PUBLICATION_IS_UPDATED_AUTOMATICALLY = "pfp_publication_is_updated_automatically"
    """ Вакансии с оплатой за контакты в откликах автоматически поднимаются раз в 3 дня """
    FREE_PROLONGATION_NOT_AVAILABLE = "free_prolongation_not_available"
    """ Не получится поднять бесплатную вакансию """
    NOT_ENOUGH_QUOTAS = "not_enough_quotas"
    """ Не хватает квот """
    NOT_ENOUGH_PURCHASED_SERVICES = "not_enough_purchased_services"
    """ Вакансия не может быть обновлена. Недостаточно купленных услуг. """
    NOT_ENOUGH_DIVISION_SERVICES = "not_enough_division_services"
    """ Закончились услуги на отдел """
    NOT_AVAILABLE_FOR_PURCHASE = "not_available_for_purchase"
    """ Вакансия не может быть обновлена. Недостающие услуги недоступны для покупки. """
    UNKNOWN = "unknown"
    """ Не получится поднять вакансию """


class ResumeHiddenFieldsEnum(StrEnum):
    NAMES_AND_PHOTO = "names_and_photo"
    """ ФИО и фотографию """
    PHONES = "phones"
    """ Все указанные в резюме телефоны """
    EMAIL = "email"
    """ Электронную почту """
    OTHER_CONTACTS = "other_contacts"
    """ Другие контакты: соцсети, мессенджеры """
    EXPERIENCE = "experience"
    """ Все места работы """


class PhoneCallStatusEnum(StrEnum):
    PICK_SUCCESSFUL = "pick_successful"
    """ Установка соединения """
    CALLING = "calling"
    """ Звонок """
    DID_NOT_CONNECT = "did_not_connect"
    """ Абонент временно недоступен """
    CALL_IN_PROGRESS = "call_in_progress"
    """ Телефонный разговор """
    CALL_ERROR = "call_error"
    """ Техническая ошибка """
    CALL_ENDED = "call_ended"
    """ Телефонный разговор завершен """


class LinkedSocialsEnum(StrEnum):
    ESIA = "esia"
    """ Госуслуги """
    VK = "vk"
    """ ВКонтакте """
    GPLUS = "gplus"
    """ Google """
    MAIL = "mail"
    """ Мой Мир@mail.ru """
    OK = "ok"
    """ Одноклассники """
    APPLE = "apple"
    """ Apple """
    LI = "li"
    """ LinkedIn """
    FB = "fb"
    """ Facebook """
    TINKOFF_BUSINESS = "tinkoff_business"
    """ T-Банк """
    TUTBY = "tutby"
    """ rabota.by """
    RSV = "rsv"
    """ Россия — страна возможностей """
    VR = "vr"
    """ Виртуальный рекрутер """


class VacancyLabelEnum(StrEnum):
    WITH_ADDRESS = "with_address"
    """ Только с адресом """
    ACCEPT_HANDICAPPED = "accept_handicapped"
    """ Только доступные для людей с инвалидностью """
    NOT_FROM_AGENCY = "not_from_agency"
    """ Без вакансий агентств """
    ACCEPT_KIDS = "accept_kids"
    """ Только доступные для соискателей от 14 лет """
    ACCREDITED_IT = "accredited_it"
    """ Только аккредитованные ИТ-компании """
    LOW_PERFORMANCE = "low_performance"
    """ Только вакансии, у которых меньше 10 откликов """
    INTERNSHIP = "internship"
    """ Стажировка """
    NIGHT_SHIFTS = "night_shifts"
    """ Вечерние или ночные смены """
    WITH_SALARY = "with_salary"
    """ Указан доход """
    ACCEPT_TEENS = "accept_teens"
    """ Только доступные для соискателей от 16 лет """


class ExperienceEnum(StrEnum):
    NOEXPERIENCE = "noExperience"
    """ Нет опыта """
    BETWEEN1AND3 = "between1And3"
    """ От 1 года до 3 лет """
    BETWEEN3AND6 = "between3And6"
    """ От 3 до 6 лет """
    MORETHAN6 = "moreThan6"
    """ Более 6 лет """


class EmploymentEnum(StrEnum):
    FULL = "full"
    """ Полная занятость """
    PART = "part"
    """ Частичная занятость """
    PROJECT = "project"
    """ Проектная работа """
    VOLUNTEER = "volunteer"
    """ Волонтерство """
    PROBATION = "probation"
    """ Стажировка """


class ScheduleEnum(StrEnum):
    FULLDAY = "fullDay"
    """ Полный день """
    SHIFT = "shift"
    """ Сменный график """
    FLEXIBLE = "flexible"
    """ Гибкий график """
    REMOTE = "remote"
    """ Удаленная работа """
    FLYINFLYOUT = "flyInFlyOut"
    """ Вахтовый метод """


class EducationLevelEnum(StrEnum):
    SECONDARY = "secondary"
    """ Среднее """
    SPECIAL_SECONDARY = "special_secondary"
    """ Среднее специальное """
    UNFINISHED_HIGHER = "unfinished_higher"
    """ Неоконченное высшее """
    HIGHER = "higher"
    """ Высшее """
    BACHELOR = "bachelor"
    """ Бакалавр """
    MASTER = "master"
    """ Магистр """
    CANDIDATE = "candidate"
    """ Кандидат наук """
    DOCTOR = "doctor"
    """ Доктор наук """


class CurrencyEnum(StrEnum):
    AZN = "AZN"
    """ Манаты """
    BYR = "BYR"
    """ Белорусские рубли """
    EUR = "EUR"
    """ Евро """
    GEL = "GEL"
    """ Грузинский лари """
    KGS = "KGS"
    """ Кыргызский сом """
    KZT = "KZT"
    """ Тенге """
    RUR = "RUR"
    """ Рубли """
    UAH = "UAH"
    """ Гривны """
    USD = "USD"
    """ Доллары """
    UZS = "UZS"
    """ Узбекский сум """


class VacancyBillingTypeEnum(StrEnum):
    FREE = "free"
    """ Бесплатная """
    STANDARD = "standard"
    """ Стандарт """
    STANDARD_PLUS = "standard_plus"
    """ Стандарт плюс """
    PREMIUM = "premium"
    """ Премиум """


class ApplicantCommentAccessTypeEnum(StrEnum):
    COWORKERS = "coworkers"
    """ Виден мне и моим коллегам """
    OWNER = "owner"
    """ Виден только мне """


class VacancyClusterEnum(StrEnum):
    AREA = "area"
    """ Регион """
    METRO = "metro"
    """ Метро """
    SALARY = "salary"
    """ Уровень дохода """
    INDUSTRY = "industry"
    """ Отрасль компании """
    SUB_INDUSTRY = "sub_industry"
    """ Сфера компании """
    EXPERIENCE = "experience"
    """ Опыт работы """
    LABEL = "label"
    """ Исключение """
    PROFESSIONAL_ROLE = "professional_role"
    """ Профессиональная роль """
    DISTRICT = "district"
    """ Район """
    EDUCATION = "education"
    """ Образование """
    ACCEPT_TEMPORARY = "accept_temporary"
    """ оформление по ГПХ или по совместительству """
    EMPLOYMENT_FORM = "employment_form"
    """ Тип занятости """
    WORK_SCHEDULE_BY_DAYS = "work_schedule_by_days"
    """ График работы """
    WORKING_HOURS = "working_hours"
    """ Рабочие часы в день """
    WORK_FORMAT = "work_format"
    """ Формат работы """
    SALARY_FREQUENCY = "salary_frequency"
    """ Частота выплат """
    SALARY_PER_MODE = "salary_per_mode"
    """ Уровень дохода """
    DRIVER_LICENSE_TYPES = "driver_license_types"
    """ Категория прав """


class DriverLicenseTypesEnum(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    BE = "BE"
    CE = "CE"
    DE = "DE"
    TM = "TM"
    TB = "TB"


class LanguageLevelEnum(StrEnum):
    A1 = "a1"
    """ A1 — Начальный """
    A2 = "a2"
    """ A2 — Элементарный """
    B1 = "b1"
    """ B1 — Средний """
    B2 = "b2"
    """ B2 — Средне-продвинутый """
    C1 = "c1"
    """ C1 — Продвинутый """
    C2 = "c2"
    """ C2 — В совершенстве """
    L1 = "l1"
    """ Родной """


class WorkingDaysEnum(StrEnum):
    ONLY_SATURDAY_AND_SUNDAY = "only_saturday_and_sunday"
    """ По субботам и воскресеньям """


class WorkingTimeIntervalsEnum(StrEnum):
    FROM_FOUR_TO_SIX_HOURS_IN_A_DAY = "from_four_to_six_hours_in_a_day"
    """ Можно сменами по 4-6 часов в день """


class WorkingTimeModesEnum(StrEnum):
    START_AFTER_SIXTEEN = "start_after_sixteen"
    """ С началом дня после 16:00 """


class VacancyTypeEnum(StrEnum):
    DIRECT = "direct"
    """ Рекламная """
    ANONYMOUS = "anonymous"
    """ Анонимная """
    CLOSED = "closed"
    """ Закрытая """
    OPEN = "open"
    """ Открытая """


class JobSearchStatusesApplicantEnum(StrEnum):
    ACTIVE_SEARCH = "active_search"
    """ Активно ищу работу """
    LOOKING_FOR_OFFERS = "looking_for_offers"
    """ Рассматриваю предложения """
    NOT_LOOKING_FOR_JOB = "not_looking_for_job"
    """ Не ищу работу """
    HAS_JOB_OFFER = "has_job_offer"
    """ Предложили работу, пока думаю """
    ACCEPTED_JOB_OFFER = "accepted_job_offer"
    """ Уже выхожу на новое место """


class JobSearchStatusesEmployerEnum(StrEnum):
    ACTIVE_SEARCH = "active_search"
    """ Активно ищет работу """
    LOOKING_FOR_OFFERS = "looking_for_offers"
    """ Рассматривает предложения """
    NOT_LOOKING_FOR_JOB = "not_looking_for_job"
    """ Не ищет работу """
    HAS_JOB_OFFER = "has_job_offer"
    """ Предложили работу, решает """
    ACCEPTED_JOB_OFFER = "accepted_job_offer"
    """ Вышел на новое место """


class EmploymentFormEnum(StrEnum):
    FULL = "FULL"
    """ Полная """
    PART = "PART"
    """ Частичная """
    PROJECT = "PROJECT"
    """ Проект """
    FLY_IN_FLY_OUT = "FLY_IN_FLY_OUT"
    """ Вахта """
    SIDE_JOB = "SIDE_JOB"
    """ Подработка """


class WorkFormatEnum(StrEnum):
    ON_SITE = "ON_SITE"
    """ На месте работодателя """
    REMOTE = "REMOTE"
    """ Удалённо """
    HYBRID = "HYBRID"
    """ Гибрид """
    FIELD_WORK = "FIELD_WORK"
    """ Разъездной """


class ResumeEmploymentFormEnum(StrEnum):
    FULL = "FULL"
    """ Постоянная работа """
    PART_TIME = "PART_TIME"
    """ Подработка """
    INTERNSHIP = "INTERNSHIP"
    """ Стажировка """
    VOLUNTEER = "VOLUNTEER"
    """ Волонтёрство """


class ResumeWorkFormatEnum(StrEnum):
    ON_SITE = "ON_SITE"
    """ На месте работодателя """
    REMOTE = "REMOTE"
    """ Удалённо """
    HYBRID = "HYBRID"
    """ Гибрид """
    FIELD_WORK = "FIELD_WORK"
    """ Разъездной """
    FLY_IN_FLY_OUT = "FLY_IN_FLY_OUT"
    """ Вахта """


class WorkingHoursEnum(StrEnum):
    HOURS_2 = "HOURS_2"
    """ 2 часа """
    HOURS_3 = "HOURS_3"
    """ 3 часа """
    HOURS_4 = "HOURS_4"
    """ 4 часа """
    HOURS_5 = "HOURS_5"
    """ 5 часов """
    HOURS_6 = "HOURS_6"
    """ 6 часов """
    HOURS_7 = "HOURS_7"
    """ 7 часов """
    HOURS_8 = "HOURS_8"
    """ 8 часов """
    HOURS_9 = "HOURS_9"
    """ 9 часов """
    HOURS_10 = "HOURS_10"
    """ 10 часов """
    HOURS_11 = "HOURS_11"
    """ 11 часов """
    HOURS_12 = "HOURS_12"
    """ 12 часов """
    HOURS_24 = "HOURS_24"
    """ 24 часа """
    FLEXIBLE = "FLEXIBLE"
    """ По договорённости """
    OTHER = "OTHER"
    """ Другое """


class FlyInFlyOutDurationEnum(StrEnum):
    DAYS_15 = "DAYS_15"
    """ 15 """
    DAYS_20 = "DAYS_20"
    """ 20 """
    DAYS_30 = "DAYS_30"
    """ 30 """
    DAYS_40 = "DAYS_40"
    """ 40 """
    DAYS_45 = "DAYS_45"
    """ 45 """
    DAYS_60 = "DAYS_60"
    """ 60 """
    DAYS_90 = "DAYS_90"
    """ 90 """
    DAYS_120 = "DAYS_120"
    """ 120 """
    DAYS_180 = "DAYS_180"
    """ 180 """
    OTHER = "OTHER"
    """ Другое """


class WorkScheduleByDaysEnum(StrEnum):
    SIX_ON_ONE_OFF = "SIX_ON_ONE_OFF"
    """ 6/1 """
    FIVE_ON_TWO_OFF = "FIVE_ON_TWO_OFF"
    """ 5/2 """
    FOUR_ON_FOUR_OFF = "FOUR_ON_FOUR_OFF"
    """ 4/4 """
    FOUR_ON_THREE_OFF = "FOUR_ON_THREE_OFF"
    """ 4/3 """
    FOUR_ON_TWO_OFF = "FOUR_ON_TWO_OFF"
    """ 4/2 """
    THREE_ON_THREE_OFF = "THREE_ON_THREE_OFF"
    """ 3/3 """
    THREE_ON_TWO_OFF = "THREE_ON_TWO_OFF"
    """ 3/2 """
    TWO_ON_TWO_OFF = "TWO_ON_TWO_OFF"
    """ 2/2 """
    TWO_ON_ONE_OFF = "TWO_ON_ONE_OFF"
    """ 2/1 """
    ONE_ON_THREE_OFF = "ONE_ON_THREE_OFF"
    """ 1/3 """
    ONE_ON_TWO_OFF = "ONE_ON_TWO_OFF"
    """ 1/2 """
    WEEKEND = "WEEKEND"
    """ По выходным """
    FLEXIBLE = "FLEXIBLE"
    """ Свободный """
    OTHER = "OTHER"
    """ Другое """


class SalaryRangeModeEnum(StrEnum):
    MONTH = "MONTH"
    """ За месяц """
    SHIFT = "SHIFT"
    """ За смену """
    HOUR = "HOUR"
    """ За час """
    FLY_IN_FLY_OUT = "FLY_IN_FLY_OUT"
    """ За вахту """
    SERVICE = "SERVICE"
    """ За услугу """


class SalaryRangeFrequencyEnum(StrEnum):
    DAILY = "DAILY"
    """ Ежедневно """
    WEEKLY = "WEEKLY"
    """ Раз в неделю """
    TWICE_PER_MONTH = "TWICE_PER_MONTH"
    """ Два раза в месяц """
    MONTHLY = "MONTHLY"
    """ Раз в месяц """
    PER_PROJECT = "PER_PROJECT"
    """ За проект """


class AgeRestrictionEnum(StrEnum):
    AGE_14_PLUS = "AGE_14_PLUS"
    """ От 14 лет """
    AGE_16_PLUS = "AGE_16_PLUS"
    """ От 16 лет """


class CivilLawContractsEnum(StrEnum):
    SELF_EMPLOYED = "SELF_EMPLOYED"
    """ с самозанятым """
    INDIVIDUAL_ENTREPRENEUR = "INDIVIDUAL_ENTREPRENEUR"
    """ с ИП """
    INDIVIDUAL_PERSON = "INDIVIDUAL_PERSON"
    """ с физлицом """


class ResumeSearchLabelEnum(StrEnum):
    ONLY_WITH_PHOTO = "only_with_photo"
    """ Только с фотографией """
    ONLY_WITH_SALARY = "only_with_salary"
    """ Не показывать резюме без зарплаты """
    ONLY_WITH_AGE = "only_with_age"
    """ Не показывать резюме без указания возраста """
    ONLY_WITH_GENDER = "only_with_gender"
    """ Не показывать резюме без указания пола """
    ONLY_WITH_VEHICLE = "only_with_vehicle"
    """ Есть личный автомобиль """
    EXCLUDE_VIEWED_BY_USER_ID = "exclude_viewed_by_user_id"
    """ Скрыть резюме, просмотренные мной """
    EXCLUDE_VIEWED_BY_EMPLOYER_ID = "exclude_viewed_by_employer_id"
    """ Скрыть резюме, просмотренные всей компанией """
    ONLY_IN_RESPONSES = "only_in_responses"
    """ Показать только из откликов и приглашений """


class ResumeSearchRelocationEnum(StrEnum):
    LIVING_OR_RELOCATION = "living_or_relocation"
    """ Живут в указанном регионе или готовы переехать в него """
    LIVING = "living"
    """ Живут в указанном регионе """
    LIVING_BUT_RELOCATION = "living_but_relocation"
    """ Живут в указанном регионе и готовы к переезду куда-либо """
    RELOCATION = "relocation"
    """ Не живут в указанном регионе, но готовы переехать в него """


class ResumeSearchOrderEnum(StrEnum):
    PUBLICATION_TIME = "publication_time"
    """ по дате изменения """
    SALARY_DESC = "salary_desc"
    """ по убыванию зарплат """
    SALARY_ASC = "salary_asc"
    """ по возрастанию зарплаты """
    RELEVANCE = "relevance"
    """ по соответствию """


class ResumeSearchExperiencePeriodEnum(StrEnum):
    ALL_TIME = "all_time"
    """ За всё время работы """
    LAST_YEAR = "last_year"
    """ За последний год """
    LAST_THREE_YEARS = "last_three_years"
    """ За последние 3 года """
    LAST_SIX_YEARS = "last_six_years"
    """ За последние 6 лет """
