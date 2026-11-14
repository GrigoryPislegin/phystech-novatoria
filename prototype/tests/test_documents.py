import asyncio
import json
import logging
import subprocess
import sys
import unittest
from contextlib import closing
from ctypes import c_ushort
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZIP_DEFLATED, ZipFile

import pypdfium2 as pdfium
from docx import Document
from docx.opc.constants import CONTENT_TYPE, RELATIONSHIP_TYPE
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from PIL import Image, ImageDraw
from pypdfium2 import raw

from prototype.documents import (
    MAX_BYTES,
    MAX_CHARS,
    DocumentReadError,
    document_diagnostic,
    read_document,
)


def write_pdf(path: Path, *page_texts: str | None) -> None:
    """Create a PDF with Helvetica text or a blank page for each argument."""
    with pdfium.PdfDocument.new() as pdf:
        for text in page_texts:
            with closing(pdf.new_page(300, 300)) as page:
                if text is None:
                    continue
                handle = raw.FPDFPageObj_NewTextObj(pdf, b'Helvetica', 14)
                with closing(pdfium.PdfObject(handle, pdf=pdf)) as obj:
                    encoded = (text + '\0').encode('utf-16-le')
                    code_units = (c_ushort * (len(encoded) // 2)).from_buffer_copy(encoded)
                    if not raw.FPDFText_SetText(obj, code_units):
                        raise RuntimeError('could not create synthetic PDF text')
                    obj.set_matrix(pdfium.PdfMatrix(e=30, f=250))
                    page.insert_obj(obj)
                    page.gen_content()
        pdf.save(path)


def add_textbox(paragraph, *, modern=False, text='Синтетический текст в рамке'):
    content = f'<w:txbxContent><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:txbxContent>'
    if modern:
        shape = f"""
        <w:drawing {nsdecls('w', 'wp', 'a')}
            xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
          <wp:inline>
            <wp:extent cx="1000000" cy="400000"/>
            <wp:docPr id="1" name="Synthetic textbox"/>
            <a:graphic>
              <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
                <wps:wsp>
                  <wps:cNvSpPr txBox="1"/>
                  <wps:spPr/>
                  <wps:txbx>{content}</wps:txbx>
                  <wps:bodyPr/>
                </wps:wsp>
              </a:graphicData>
            </a:graphic>
          </wp:inline>
        </w:drawing>
        """
    else:
        shape = f"""
        <w:pict {nsdecls('w')} xmlns:v="urn:schemas-microsoft-com:vml">
          <v:shape id="SyntheticTextbox" style="width:120pt;height:30pt">
            <v:textbox>{content}</v:textbox>
          </v:shape>
        </w:pict>
        """
    paragraph.add_run()._element.append(parse_xml(shape))


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))

    def test_extracts_pdf_pages_in_order(self):
        path = self.directory / 'text.pdf'
        write_pdf(path, 'Synthetic Python experience', 'Synthetic SQL experience')
        self.assertEqual(
            read_document(path),
            'Synthetic Python experience\n\nSynthetic SQL experience',
        )

    def test_extracts_docx_paragraphs_and_table_in_order(self):
        path = self.directory / 'table.docx'
        document = Document()
        document.add_paragraph('Синтетические навыки')
        table = document.add_table(rows=3, cols=3)
        rows = [('Язык', 'Уровень', 'Стаж'), ('', '', ''), ('Python', '', '3 года')]
        for row, values in zip(table.rows, rows):
            for cell, text in zip(row.cells, values):
                cell.text = text
        document.add_paragraph('Синтетические проекты')
        document.save(path)
        self.assertEqual(
            read_document(path),
            'Синтетические навыки\nЯзык | Уровень | Стаж\n |  | \n'
            'Python |  | 3 года\nСинтетические проекты',
        )

    def test_extracts_docx_with_only_table_text(self):
        path = self.directory / 'table-only.docx'
        document = Document()
        table = document.add_table(rows=1, cols=2)
        table.cell(0, 0).text = 'Python'
        table.cell(0, 1).text = '3 года'
        document.save(path)
        self.assertEqual(read_document(path), 'Python | 3 года')

    def test_extracts_nested_docx_tables_with_unicode_in_order(self):
        path = self.directory / 'nested.docx'
        document = Document()
        document.add_paragraph('До таблицы\nВторая строка\tё')
        table = document.add_table(rows=1, cols=2)
        left, right = table.rows[0].cells
        left.text = 'До вложенной таблицы'
        nested = left.add_table(rows=2, cols=2)
        nested.cell(0, 0).text = '東京'
        nested.cell(0, 1).text = 'Уровень'
        nested.cell(1, 0).text = 'Go'
        nested.cell(1, 1).text = '3 года'
        left.paragraphs[-1].text = 'После вложенной таблицы'
        right.text = 'Правая ячейка'
        document.add_paragraph('После таблицы')
        document.save(path)
        self.assertEqual(
            read_document(path),
            'До таблицы\nВторая строка\tё\nДо вложенной таблицы\n'
            '東京 | Уровень\nGo | 3 года\nПосле вложенной таблицы | Правая ячейка\n'
            'После таблицы',
        )

    def test_reads_nonempty_docx_headers_and_footers(self):
        for variant in ('header', 'footer', 'first_page_header', 'even_page_footer'):
            with self.subTest(variant=variant):
                path = self.directory / f'{variant}.docx'
                document = Document()
                document.add_paragraph('Синтетический основной текст')
                section = document.sections[0]
                section.different_first_page_header_footer = True
                document.settings.odd_and_even_pages_header_footer = True
                getattr(section, variant).paragraphs[0].text = 'Обязательное условие'
                document.save(path)
                text = read_document(path)
                self.assertIn('Обязательное условие', text)
                self.assertIn('Синтетический основной текст', text)

    def test_header_tables_and_linked_sections_are_read_once(self):
        from docx.shared import Inches
        path = self.directory / 'header-tables.docx'
        document = Document()
        section = document.sections[0]
        section.header.paragraphs[0].text = 'Header contact'
        table = section.header.add_table(rows=1, cols=2, width=Inches(5))
        table.cell(0, 0).text = 'Python'
        table.cell(0, 1).text = '5 years'
        section.footer.paragraphs[0].text = 'Footer note'
        document.add_paragraph('Body experience')
        document.add_section()
        document.add_paragraph('Other section')
        document.save(path)
        text = read_document(path)
        self.assertEqual(text.count('Header contact'), 1)
        self.assertEqual(text.count('Footer note'), 1)
        self.assertIn('Python | 5 years', text)
        self.assertLess(text.index('Header contact'), text.index('Body experience'))
        self.assertGreater(text.index('Footer note'), text.index('Other section'))

    def test_inactive_and_historical_headers_are_not_candidate_evidence(self):
        from docx.oxml.ns import qn
        path = self.directory / 'inactive-headers.docx'
        document = Document()
        section = document.sections[0]
        section.first_page_header.paragraphs[0].text = 'Inactive first page'
        section.even_page_footer.paragraphs[0].text = 'Inactive even page'
        section.header.paragraphs[0].text = 'Historical header'
        # Move every default header reference into historical section properties.
        for candidate in list(section._sectPr.findall(qn('w:headerReference'))):
            if candidate.get(qn('w:type')) == 'default':
                old = parse_xml(f'<w:sectPrChange {nsdecls("w")}><w:sectPr/></w:sectPrChange>')
                old[0].append(candidate)
                section._sectPr.append(old)
        document.add_paragraph('Current body')
        document.save(path)
        self.assertEqual(read_document(path), 'Current body')

    def test_first_page_header_inherited_when_enabled_in_later_section(self):
        path = self.directory / 'inherited-first-header.docx'
        document = Document()
        document.sections[0].first_page_header.paragraphs[0].text = 'Inherited first header'
        document.add_paragraph('First body')
        later = document.add_section()
        later.different_first_page_header_footer = True
        document.add_paragraph('Later body')
        document.save(path)
        text = read_document(path)
        self.assertEqual(text.count('Inherited first header'), 1)

    def test_unread_header_textbox_still_fails_explicitly(self):
        path = self.directory / 'header-textbox.docx'
        document = Document()
        document.add_paragraph('Body')
        add_textbox(document.sections[0].header.paragraphs[0])
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^docx_shape_text$'):
            read_document(path)

    def test_header_only_text_and_combined_size_limit(self):
        path = self.directory / 'header-only.docx'
        document = Document()
        document.sections[0].header.paragraphs[0].text = 'Header content'
        document.save(path)
        self.assertEqual(read_document(path), 'Header content')
        document.add_paragraph('Body content')
        document.save(path)
        with patch('prototype.documents.MAX_CHARS', 20):
            with self.assertRaisesRegex(ValueError, '^document_text_too_long$'):
                read_document(path)

    def test_rejects_docx_textboxes_with_visible_text(self):
        for modern in (False, True):
            with self.subTest(modern=modern):
                path = self.directory / 'textbox.docx'
                document = Document()
                paragraph = document.add_paragraph('Синтетический основной текст')
                add_textbox(paragraph, modern=modern)
                document.save(path)
                with self.assertRaisesRegex(ValueError, '^docx_shape_text$'):
                    read_document(path)

    def test_accepts_blank_docx_header_footer_and_textbox(self):
        path = self.directory / 'blank-decorations.docx'
        document = Document()
        section = document.sections[0]
        section.header.paragraphs[0].text = ' \t'
        section.footer.paragraphs[0].text = ''
        paragraph = document.add_paragraph('Синтетический основной текст')
        add_textbox(paragraph, text='   ')
        document.save(path)
        self.assertEqual(read_document(path), 'Синтетический основной текст')

    def test_rejects_legacy_wordart_text_in_docx(self):
        path = self.directory / 'wordart.docx'
        document = Document()
        paragraph = document.add_paragraph('Синтетический основной текст')
        paragraph.add_run()._element.append(parse_xml(f"""
            <w:pict {nsdecls('w')} xmlns:v="urn:schemas-microsoft-com:vml">
              <v:shape id="SyntheticWordArt">
                <v:path textpathok="true"/>
                <v:textpath on="true" string="Обязательное условие"/>
              </v:shape>
            </w:pict>
        """))
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^docx_shape_text$'):
            read_document(path)

    def test_rejects_docx_with_text_in_linked_chart_part(self):
        path = self.directory / 'chart.docx'
        document = Document()
        paragraph = document.add_paragraph('Синтетический основной текст')
        chart_xml = f"""
        <c:chartSpace {nsdecls('c', 'a')}>
          <c:chart><c:title><c:tx><c:rich><a:bodyPr/>
            <a:p><a:r><a:t>Обязательное условие</a:t></a:r></a:p>
          </c:rich></c:tx></c:title><c:plotArea/></c:chart>
        </c:chartSpace>
        """
        chart = Part(PackURI('/word/charts/chart1.xml'), CONTENT_TYPE.DML_CHART,
                     chart_xml.encode('utf-8'), document.part.package)
        relationship_id = document.part.relate_to(chart, RELATIONSHIP_TYPE.CHART)
        paragraph.add_run()._element.append(parse_xml(f"""
        <w:drawing {nsdecls('w', 'wp', 'a', 'c', 'r')}>
          <wp:inline>
            <wp:extent cx="1000000" cy="400000"/>
            <wp:docPr id="1" name="Synthetic chart"/>
            <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">
              <c:chart r:id="{relationship_id}"/>
            </a:graphicData></a:graphic>
          </wp:inline>
        </w:drawing>
        """))
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^docx_unsupported_structure$'):
            read_document(path)

    def test_rejects_docx_with_legacy_checklist_symbols(self):
        path = self.directory / 'checklist.docx'
        document = Document()
        for symbol, label in [('F0FE', 'Удалённо'), ('F0FD', 'Офис')]:
            paragraph = document.add_paragraph()
            paragraph.add_run()._element.append(parse_xml(
                f'<w:sym {nsdecls("w")} w:font="Wingdings" w:char="{symbol}"/>'
            ))
            paragraph.add_run(f' {label}')
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^docx_unsupported_structure$'):
            read_document(path)

    def test_rejects_docx_text_inside_unread_body_wrapper(self):
        path = self.directory / 'content-control.docx'
        document = Document()
        paragraph = document.add_paragraph('Синтетический основной текст')
        paragraph._element.addnext(parse_xml(f"""
            <w:sdt {nsdecls('w')}>
              <w:sdtPr/>
              <w:sdtContent><w:p><w:r><w:t>Обязательное условие</w:t></w:r></w:p></w:sdtContent>
            </w:sdt>
        """))
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^docx_unsupported_structure$'):
            read_document(path)

    def test_rejects_corrupted_files(self):
        for suffix, content in [
            ('.pdf', b'%PDF-1.7\nincomplete file\n'),
            ('.docx', b'not a Word package'),
        ]:
            with self.subTest(suffix=suffix):
                path = self.directory / f'corrupted{suffix}'
                path.write_bytes(content)
                with self.assertRaisesRegex(ValueError, '^document_unreadable$'):
                    read_document(path)

    def test_rejects_docx_with_wrong_content_type(self):
        original = self.directory / 'original.docx'
        Document().save(original)
        path = self.directory / 'wrong-content-type.docx'
        with ZipFile(original) as source, ZipFile(path, 'w') as target:
            for member in source.infolist():
                content = source.read(member)
                if member.filename == '[Content_Types].xml':
                    content = content.replace(
                        CONTENT_TYPE.WML_DOCUMENT_MAIN.encode(), b'application/xml'
                    )
                target.writestr(member, content)
        with self.assertRaisesRegex(ValueError, '^document_unreadable$'):
            read_document(path)

    def test_rejects_pdf_scan_without_text_layer(self):
        path = self.directory / 'scan.pdf'
        with Image.new('RGB', (200, 80), 'white') as image:
            ImageDraw.Draw(image).text((12, 20), 'Synthetic skills', fill='black')
            image.save(path)
        with self.assertRaisesRegex(ValueError, '^ocr_required_or_empty_page$'):
            read_document(path)

    def test_rejects_pdf_with_one_empty_page(self):
        path = self.directory / 'partly-empty.pdf'
        write_pdf(path, 'Synthetic skills', None, 'Synthetic experience')
        with self.assertRaisesRegex(ValueError, '^ocr_required_or_empty_page$'):
            read_document(path)

    def test_rejects_empty_docx(self):
        path = self.directory / 'empty.docx'
        document = Document()
        document.add_paragraph(' \t')
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^document_empty$'):
            read_document(path)

    def test_rejects_docx_with_empty_table(self):
        path = self.directory / 'empty-table.docx'
        document = Document()
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text = ' \t'
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^document_empty$'):
            read_document(path)

    def test_rejects_docx_with_empty_nested_table(self):
        path = self.directory / 'empty-nested-table.docx'
        document = Document()
        cell = document.add_table(rows=1, cols=1).cell(0, 0)
        cell.add_table(rows=2, cols=2)
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^document_empty$'):
            read_document(path)

    def test_extracts_each_merged_docx_cell_once(self):
        path = self.directory / 'merged-cells.docx'
        document = Document()
        table = document.add_table(rows=3, cols=2)
        table.cell(0, 0).merge(table.cell(0, 1)).text = 'Общий заголовок'
        table.cell(1, 0).merge(table.cell(2, 0)).text = 'Общая категория'
        table.cell(1, 1).text = 'Первая строка'
        table.cell(2, 1).text = 'Вторая строка'
        document.save(path)
        self.assertEqual(read_document(path),
                         'Общий заголовок\nОбщая категория | Первая строка\n | Вторая строка')

    def test_rejects_pdf_over_file_size_limit(self):
        path = self.directory / 'oversized.pdf'
        write_pdf(path, 'Synthetic skills')
        with path.open('r+b') as file:
            file.truncate(MAX_BYTES + 1)
        with self.assertRaisesRegex(ValueError, '^input_too_large$'):
            read_document(path)

    def test_rejects_pdf_over_page_limit(self):
        path = self.directory / 'too-many-pages.pdf'
        write_pdf(path, *([None] * 101))
        with self.assertRaisesRegex(ValueError, '^too_many_pages$'):
            read_document(path)

    def test_docx_extracted_text_limit(self):
        path = self.directory / 'long-text.docx'
        document = Document()
        text = 'x' * MAX_CHARS
        document.add_paragraph(text)
        document.save(path)
        self.assertEqual(read_document(path), text)
        document.add_paragraph('one more line')
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^document_text_too_long$'):
            read_document(path)

    def test_rejects_docx_over_uncompressed_size_limit(self):
        path = self.directory / 'oversized.docx'
        document = Document()
        document.add_paragraph('Synthetic skills')
        document.save(path)
        with ZipFile(path, 'a', compression=ZIP_DEFLATED) as archive:
            padding = b'<padding>' + b' ' * 20_000_000 + b'</padding>'
            archive.writestr('word/synthetic-padding.xml', padding)
        with self.assertRaisesRegex(ValueError, '^document_expansion_limit$'):
            read_document(path)

    def test_pdf_library_errors_expose_only_safe_codes(self):
        path = self.directory / 'SYNTHETIC_PRIVATE_FILENAME.pdf'
        write_pdf(path, 'Synthetic skills')
        previous_factory = logging.getLogRecordFactory()
        self.addCleanup(logging.setLogRecordFactory, previous_factory)

        def fail(*args, **kwargs):
            logging.getLogger('pdfminer.synthetic').warning('synthetic data %s', path)
            raise ValueError('SYNTHETIC_PRIVATE_EXCEPTION')

        with patch('pdfplumber.open', side_effect=fail), self.assertLogs('pdfminer') as logs:
            with self.assertRaisesRegex(ValueError, '^document_unreadable$') as caught:
                read_document(path)
        self.assertNotIn(path.name, '\n'.join(logs.output))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_shared_diagnostic_only_accepts_known_codes(self):
        self.assertEqual(document_diagnostic(ValueError('invalid_job_set'))['code'], 'invalid_job_set')
        for error in (
            ValueError('SYNTHETIC_PRIVATE_MESSAGE'),
            ValueError('docx_shape_text'),
            DocumentReadError('SYNTHETIC_PRIVATE_MESSAGE'),
        ):
            self.assertEqual(document_diagnostic(error)['code'], 'document_unreadable')
        self.assertEqual(document_diagnostic(DocumentReadError('docx_shape_text'))['code'], 'docx_shape_text')

    def test_inspection_reports_each_file_without_echoing_input(self):
        missing = self.directory / 'SYNTHETIC_PRIVATE_MISSING.docx'
        corrupt = self.directory / 'SYNTHETIC_PRIVATE_BAD.docx'
        corrupt.write_bytes(b'SYNTHETIC_PRIVATE_CORRUPT')
        invalid_text = self.directory / 'SYNTHETIC_PRIVATE_ENCODING.txt'
        invalid_text.write_bytes(b'SYNTHETIC_PRIVATE_CONTENT\xff')
        empty = self.directory / 'SYNTHETIC_PRIVATE_EMPTY.md'
        empty.touch()
        unsupported = self.directory / 'SYNTHETIC_PRIVATE_TYPE.rtf'
        unsupported.write_text('SYNTHETIC_PRIVATE_CONTENT', encoding='utf-8')
        valid = self.directory / 'SYNTHETIC_PRIVATE_GOOD.md'
        valid.write_bytes('Пример\r\nтекста'.encode('utf-8-sig'))
        linked = self.directory / 'SYNTHETIC_PRIVATE_SYMLINK.md'
        linked.symlink_to(valid)
        header = self.directory / 'SYNTHETIC_PRIVATE_HEADER.docx'
        document = Document()
        document.add_paragraph('SYNTHETIC_PRIVATE_CONTENT')
        document.sections[0].header.paragraphs[0].text = 'SYNTHETIC_PRIVATE_HEADER_TEXT'
        document.save(header)
        paths = [missing, corrupt, invalid_text, empty, unsupported, valid, linked, header]
        result = subprocess.run(
            [sys.executable, '-m', 'prototype.documents', *map(str, paths)],
            capture_output=True, text=True, check=False,
            cwd=Path(__file__).resolve().parents[2],
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn('SYNTHETIC_PRIVATE', result.stdout + result.stderr)
        files = json.loads(result.stdout)
        self.assertEqual([item['file'] for item in files], list(range(1, len(paths) + 1)))
        self.assertEqual([item.get('code') for item in files], [
            'input_invalid', 'document_unreadable', 'document_encoding_invalid',
            'document_empty', 'input_unsupported', None, 'input_symlink', None,
        ])
        self.assertEqual(files[5], {'file': 6, 'status': 'ok', 'characters': len('Пример\nтекста')})
        for item in files:
            if item['status'] == 'error':
                self.assertTrue(item['reason'])
                self.assertTrue(item['action'])

    def test_file_count_is_preflighted_by_application(self):
        from prototype.application import load_documents

        jobs = self.directory / 'jobs'
        jobs.mkdir()
        resume = self.directory / 'resume.txt'
        resume.write_text('synthetic')
        for i in range(20):
            (jobs / f'{i:02}.txt').write_text('synthetic')
        reader = Mock(return_value='synthetic')

        _, parsed, _ = load_documents(resume, jobs, reader=reader)
        self.assertEqual(len(parsed), 20)
        self.assertEqual(reader.call_count, 21)  # 20 jobs and the resume
        reader.reset_mock()
        (jobs / '20.txt').write_text('synthetic')
        with self.assertRaisesRegex(ValueError, '^invalid_job_set$'):
            load_documents(resume, jobs, reader=reader)
        reader.assert_not_called()

    def test_invalid_files_stop_run_before_privacy_and_model(self):
        from prototype.__main__ import execute

        jobs = self.directory / 'jobs'
        jobs.mkdir()
        resume = self.directory / 'resume.txt'
        resume.write_text('synthetic')
        args = SimpleNamespace(command='run', resume=resume, jobs=jobs, out=self.directory / 'out')
        for filename, contents, code in [
            ('empty.docx', b'', 'document_empty'),
            ('corrupt.docx', b'synthetic invalid archive', 'document_unreadable'),
            ('too-long.txt', b'x' * (MAX_CHARS + 1), 'document_text_too_long'),
            ('too-large.txt', b'x' * (MAX_BYTES + 1), 'input_too_large'),
            ('unsupported.rtf', b'synthetic', 'input_unsupported'),
        ]:
            with self.subTest(code=code):
                path = jobs / filename
                path.write_bytes(contents)
                try:
                    with patch('prototype.__main__.local_privacy') as privacy, patch('prototype.__main__.Model') as model:
                        with self.assertRaisesRegex(ValueError, f'^{code}$'):
                            asyncio.run(execute(args))
                        privacy.assert_not_called()
                        model.assert_not_called()
                finally:
                    path.unlink()
