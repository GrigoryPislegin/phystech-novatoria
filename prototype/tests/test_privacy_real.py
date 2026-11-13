"""Local NER acceptance corpus; skipped explicitly if public models are absent."""
import asyncio
from pathlib import Path
import unittest
from unittest.mock import patch
from prototype.privacy_core import Detector, LocalPrivacy, REFERENCE
from prototype.privacy_core.models import load


@unittest.skipUnless(Path('data/private/privacy-models/slovnet_ner_news_v1.tar').is_file(), 'public NER models not installed')
class RealPrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector(load('data/private/privacy-models'))

    def test_synthetic_contacts_names_places_and_companies(self):
        examples = [
            ('vk.com/id123456', ['id123456']),
            ('LinkedIn — j_smith', ['j_smith']),
            ('Год рождения: 1990', ['1990']),
            ('День рождения: 31 декабря 1990', ['31', '1990']),
            ('Email — info@localhost', ['info@localhost']),
            ('Сайт: example.org/profile/john-smith', ['john-smith']),
            ('Адрес — ул. Ленина, д. 12, кв. 45', ['Ленина', '12', '45']),
            ('Адрес\nул. Лесная, д. 12, кв. 45', ['Лесная', '12', '45']),
            ('Дата рождения — 1990-12-31', ['1990', '12-31']),
            ('Telegram — test_user', ['test_user']),
            ('LinkedIn linkedin.com/in/test_user', ['test_user']),
            ('Telegram test_user', ['test_user']),
            ('АНДРЕЕВ ПЁТР ВЛАДИМИРОВИЧ\nBackend-разработчик', ['АНДРЕЕВ', 'ПЁТР', 'ВЛАДИМИРОВИЧ']),
            ('Мария Петрова\nМосква\nРаботала в Альфа-Банке три года.', ['Мария', 'Петрова', 'Москва', 'Альфа-Банке']),
            ('ФИО: John Smith\nАдрес: London, Baker Street 22\nPython 3 года.', ['John', 'Smith', 'Baker']),
            ('Дата рождения: 01.02.1990\nTelegram: test_user\nEmail: test@example.org', ['1990', 'test_user', 'test@example.org']),
            ('Работала с SQL 1 год как с подрядчиком.', ['SQL']),
            ('Создавала отчёты в Excel, где работала бухгалтером.', ['Excel']),
        ]
        for text, values in examples:
            with self.subTest(case=examples.index((text, values))):
                # Deliberately include short address/date digits in the opaque
                # nonce: their occurrence inside an issued reference is not PII.
                with patch('prototype.privacy_core.secrets.token_hex', return_value='1231451990abcdef'):
                    privacy = LocalPrivacy(self.detector)
                safe = asyncio.run(privacy.redact(text))
                visible = REFERENCE.sub(lambda m: '' if m.group() in privacy.issued_refs else m.group(), safe)
                for value in values: self.assertNotIn(value, visible)
                privacy.close()

    def test_professional_skills_and_negation_survive(self):
        text = 'Разрабатывал на Python 3 года. Использовал SQL 1 год. Не работал с Java.'
        privacy = LocalPrivacy(self.detector)
        self.assertEqual(asyncio.run(privacy.redact(text)), text)
        privacy.close()

    def test_contact_word_in_professional_sentence_does_not_swallow_experience(self):
        privacy = LocalPrivacy(self.detector)
        result = asyncio.run(privacy.redact('Разрабатывал Telegram бота на Python 3 года.'))
        self.assertIn('бота на Python 3 года.', result)
        self.assertTrue(privacy.summary()['professional_information_may_be_hidden'])
        privacy.close()

    def test_inline_email_label_does_not_remove_next_professional_sentence(self):
        from scripts.privacy_smoke import check
        self.assertEqual(asyncio.run(check())['status'], 'pass')
