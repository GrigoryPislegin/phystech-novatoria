import unittest
from contextlib import closing
from ctypes import c_ushort
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import pypdfium2 as pdfium
from docx import Document
from docx.opc.constants import CONTENT_TYPE
from PIL import Image, ImageDraw
from pypdfium2 import raw

from prototype.documents import MAX_BYTES, MAX_CHARS, read_document


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
        write_pdf(path, 'Synthetic skills', None)
        with self.assertRaisesRegex(ValueError, '^ocr_required_or_empty_page$'):
            read_document(path)

    def test_rejects_empty_docx(self):
        path = self.directory / 'empty.docx'
        document = Document()
        document.add_paragraph(' \t')
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^empty_or_oversized_text$'):
            read_document(path)

    def test_rejects_docx_with_empty_table(self):
        path = self.directory / 'empty-table.docx'
        document = Document()
        table = document.add_table(rows=2, cols=2)
        table.cell(0, 0).text = ' \t'
        document.save(path)
        with self.assertRaisesRegex(ValueError, '^empty_or_oversized_text$'):
            read_document(path)

    def test_rejects_pdf_over_file_size_limit(self):
        path = self.directory / 'oversized.pdf'
        write_pdf(path, 'Synthetic skills')
        with path.open('r+b') as file:
            file.truncate(MAX_BYTES + 1)
        with self.assertRaisesRegex(ValueError, '^document_size_or_missing$'):
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
        with self.assertRaisesRegex(ValueError, '^empty_or_oversized_text$'):
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
