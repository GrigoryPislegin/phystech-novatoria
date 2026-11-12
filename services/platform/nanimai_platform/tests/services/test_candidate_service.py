import pytest

from nanimai_platform import domain, services


@pytest.mark.parametrize(
    ("test_name", "resume", "expected"),
    [
        (
            "empty case",
            "",
            {},
        ),
        (
            "email case 1",
            "Contact me at john.doe@example.com",
            {domain.ContactTypeEnum.EMAIL: "john.doe@example.com"},
        ),
        (
            "email case 2",
            "EMAIL: fixture1@example.com",
            {domain.ContactTypeEnum.EMAIL: "fixture1@example.com"},
        ),
        (
            "phone with +7",
            "Phone: +7 (999) 123-45-67",
            {domain.ContactTypeEnum.PHONE: "+7 (999) 123-45-67"},
        ),
        (
            "phone with 8",
            "Телефон: 8-999-123-45-67",
            {domain.ContactTypeEnum.PHONE: "8-999-123-45-67"},
        ),
        (
            "phone norm form",
            "Call me: 79991234567",
            {domain.ContactTypeEnum.PHONE: "79991234567"},
        ),
        (
            "telegram link",
            "Telegram: t.me/username",
            {domain.ContactTypeEnum.TELEGRAM: "t.me/username"},
        ),
        (
            "telegram tag",
            "TG: @johndoe",
            {domain.ContactTypeEnum.TELEGRAM: "t.me/johndoe"},
        ),
        (
            "telegram link dirty",
            "Contact: TEST t.me/User_Name123 321",
            {domain.ContactTypeEnum.TELEGRAM: "t.me/User_Name123"},
        ),
        (
            "telegram multiple invalid one valid",
            "I have created: @superbot, t.me/anti_bot, @spamBot, @botBot, fixture2@example.com "
            + "@ax1bot. my tg: t.me/username, available at @shopify_bot, and at @rAnbOmCasEbOt",
            {
                domain.ContactTypeEnum.EMAIL: "fixture2@example.com",
                domain.ContactTypeEnum.TELEGRAM: "t.me/username",
            },
        ),
        (
            "telegram multiple valid take last",
            "I am known as @user1, t.me/fancy_pants_user, @work_user, t.me/username, @anton",
            {
                domain.ContactTypeEnum.TELEGRAM: "t.me/anton",
            },
        ),
        (
            "telegram bot tag",
            "My bot: @supportbot",
            {},
        ),
        (
            "telegram bot link",
            "Check t.me/helperBot",
            {},
        ),
        (
            "telegram bot text",
            "Use @TestBOT for help",
            {},
        ),
        (
            "telegram too short tag",
            "@abcd is my handle",
            {},
        ),
        (
            "telegram tag starts with number",
            "@1username",
            {},
        ),
        (
            "telegram does not collide with email",
            "fixture3@example.com has no telegram",
            {domain.ContactTypeEnum.EMAIL: "fixture3@example.com"},
        ),
        (
            "whatsapp case capture both",
            "WhatsApp: wa.me/79991234567",
            {
                domain.ContactTypeEnum.PHONE: "79991234567",
                domain.ContactTypeEnum.WHATSAPP: "wa.me/79991234567",
            },
        ),
        (
            "whatsapp case one",
            "WA: wa.me/9096654708",
            {
                domain.ContactTypeEnum.WHATSAPP: "wa.me/9096654708",
            },
        ),
        (
            "multiple contacts",
            "Email: john@example.com, Phone: +7 (999) 123-45-67, TG: @johndoe",
            {
                domain.ContactTypeEnum.EMAIL: "john@example.com",
                domain.ContactTypeEnum.PHONE: "+7 (999) 123-45-67",
                domain.ContactTypeEnum.TELEGRAM: "t.me/johndoe",
            },
        ),
        (
            "all contacts",
            "john@example.com +79991234567 t.me/johndoe wa.me/79991234567",
            {
                domain.ContactTypeEnum.EMAIL: "john@example.com",
                domain.ContactTypeEnum.PHONE: "+79991234567",
                domain.ContactTypeEnum.TELEGRAM: "t.me/johndoe",
                domain.ContactTypeEnum.WHATSAPP: "wa.me/79991234567",
            },
        ),
        (
            "real world 1",
            """
            Иван Иванов
            Email: fixture4@example.com
            Телефон: +7 (926) 123-45-67
            Telegram: @ivan_ivanov
            """,
            {
                domain.ContactTypeEnum.EMAIL: "fixture4@example.com",
                domain.ContactTypeEnum.PHONE: "+7 (926) 123-45-67",
                domain.ContactTypeEnum.TELEGRAM: "t.me/ivan_ivanov",
            },
        ),
    ],
)
def test__extract_contacts_from_resume(
    test_name: str,
    resume: str,
    expected: dict[domain.ContactTypeEnum, str],
) -> None:
    got = services.CandidateService._extract_contacts_from_resume(resume)  # pyright: ignore[reportPrivateUsage]
    decsription = f"TEST[{test_name}: Expected {expected}, Got {got}"
    if got != expected:
        pytest.fail(decsription)
