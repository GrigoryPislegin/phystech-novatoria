"""Local text extraction and diagnostics shared by file transports."""

from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from stat import S_ISLNK, S_ISREG
from zipfile import ZipFile

from .privacy import protect_dependency_logs

MAX_BYTES = 5_000_000
MAX_CHARS = 60_000
MAX_PDF_PAGES = 100
MAX_DOCX_EXPANDED_BYTES = 20_000_000

_DIAGNOSTICS = {
    'input_invalid': (
        'По указанному пути нет обычного файла.',
        'Выберите существующий файл.',
    ),
    'input_access_denied': (
        'Нет доступа к файлу.',
        'Проверьте права на чтение или выберите доступную копию.',
    ),
    'input_symlink': (
        'Указана символическая ссылка.',
        'Выберите сам файл.',
    ),
    'input_unsupported': (
        'Формат файла не поддерживается.',
        'Сохраните файл в DOCX, PDF с текстовым слоем, TXT или MD.',
    ),
    'input_too_large': (
        'Файл больше 5 МБ (5 000 000 байт).',
        'Уменьшите размер файла, сохранив весь нужный текст.',
    ),
    'invalid_job_set': (
        'Нужно от 1 до 20 файлов вакансий.',
        'Проверьте количество файлов в папке вакансий.',
    ),
    'document_empty': (
        'В файле нет текста для анализа.',
        'Проверьте, что документ содержит текст, и сохраните его снова.',
    ),
    'document_text_too_long': (
        'Извлечённый текст длиннее 60 000 символов.',
        'Сократите текст, сохранив важные условия и сведения.',
    ),
    'document_encoding_invalid': (
        'Текстовый файл не читается в кодировке UTF-8.',
        'Пересохраните TXT или MD в UTF-8.',
    ),
    'document_text_invalid': (
        'В тексте есть нулевые символы.',
        'Заново экспортируйте файл из исходного документа.',
    ),
    'too_many_pages': (
        'В PDF больше 100 страниц.',
        'Сохраните нужные страницы в PDF объёмом до 100 страниц.',
    ),
    'ocr_required_or_empty_page': (
        'В PDF нет страниц или хотя бы одна страница без извлекаемого текста.',
        'Удалите пустые страницы или сохраните PDF с текстовым слоем на каждой странице.',
    ),
    'document_expansion_limit': (
        'Данные DOCX после распаковки превышают 20 МБ.',
        'Уменьшите размер вложений или сохраните нужный текст в новом файле.',
    ),
    'docx_header_footer': (
        'В колонтитулах DOCX обнаружен текст или объект с отдельным содержимым.',
        'Перенесите нужную информацию в основной текст и очистите колонтитулы.',
    ),
    'docx_shape_text': (
        'В фигуре или текстовом поле DOCX обнаружен текст.',
        'Перенесите текст из фигуры или поля в основной текст документа.',
    ),
    'docx_unsupported_structure': (
        'В DOCX есть содержимое, которое не читается как абзацы или таблицы.',
        'Скопируйте нужное содержимое в новый DOCX обычными абзацами и таблицами.',
    ),
    'parser_dependency_missing': (
        'Не удалось загрузить библиотеку для чтения этого формата.',
        'Установите зависимости по инструкции запуска прототипа.',
    ),
    'document_unreadable': (
        'Не удалось прочитать файл.',
        'Откройте исходник и сохраните исправную копию без пароля.',
    ),
}
_PREFLIGHT_CODES = {
    'input_invalid', 'input_symlink', 'input_unsupported', 'input_too_large', 'invalid_job_set',
}


class DocumentReadError(ValueError):
    """A parser failure represented by a fixed public code."""

    def __init__(self, code: str):
        self.code = code if code in _DIAGNOSTICS else 'document_unreadable'
        super().__init__(self.code)


def document_diagnostic(error: Exception) -> dict[str, str]:
    """Format a parser or application preflight error for CLI and web."""
    code = 'document_unreadable'
    if isinstance(error, DocumentReadError):
        code = error.code
    elif type(error) is ValueError and len(error.args) == 1:
        message = error.args[0]
        if type(message) is str and message in _PREFLIGHT_CODES:
            code = message
    if code not in _DIAGNOSTICS:
        code = 'document_unreadable'
    reason, action = _DIAGNOSTICS[code]
    return {'code': code, 'reason': reason, 'action': action}


def _read_pdf(stream) -> str:
    import pdfplumber

    with pdfplumber.open(stream) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise DocumentReadError('too_many_pages')
        if not pdf.pages:
            raise DocumentReadError('ocr_required_or_empty_page')
        parts = []
        for page in pdf.pages:
            text = page.extract_text() or ''
            if not text.strip():
                raise DocumentReadError('ocr_required_or_empty_page')
            parts.append(text)
        return '\n\n'.join(parts)


def _check_docx_structure(document) -> None:
    from docx.oxml.ns import qn

    body = document.element.body
    word_text, shape_text, math_text = (qn(tag) for tag in ('w:t', 'a:t', 'm:t'))
    textbox = qn('w:txbxContent')
    vml_textpath = '{urn:schemas-microsoft-com:vml}textpath'
    linked_drawings = (qn('c:chart'), qn('dgm:relIds'))

    def contains_text(element, *tags):
        return any((node.text or '').strip() for node in element.iter(*tags))

    def contains_wordart(element):
        return any(node.get('string', '').strip() for node in element.iter(vml_textpath))

    references = body.iter(qn('w:headerReference'), qn('w:footerReference'))
    relationship_id = qn('r:id')
    for part_id in dict.fromkeys(reference.get(relationship_id) for reference in references):
        element = document.part.related_parts[part_id].element
        if (contains_text(element, word_text, shape_text, math_text)
                or contains_wordart(element)
                or next(element.iter(qn('w:sym'), *linked_drawings), None) is not None):
            raise DocumentReadError('docx_header_footer')

    if contains_text(body, shape_text) or contains_wordart(body):
        raise DocumentReadError('docx_shape_text')
    for field in body.iter(textbox):
        if contains_text(field, word_text, math_text):
            raise DocumentReadError('docx_shape_text')

    unread_elements = (
        qn('w:altChunk'), qn('w:footnoteReference'), qn('w:endnoteReference'),
        qn('w:sym'), *linked_drawings,
    )
    if next(body.iter(*unread_elements), None) is not None:
        raise DocumentReadError('docx_unsupported_structure')

    # Check that text occurs on the same XML paths the extractor reads.
    # Content controls and tracked insertions can hide otherwise ordinary paragraphs.
    allowed_parents = {
        qn('w:t'): {qn('w:r')},
        qn('w:r'): {qn('w:p'), qn('w:hyperlink')},
        qn('w:hyperlink'): {qn('w:p')},
        qn('w:p'): {qn('w:body'), qn('w:tc')},
        qn('w:tc'): {qn('w:tr')},
        qn('w:tr'): {qn('w:tbl')},
        qn('w:tbl'): {qn('w:body'), qn('w:tc')},
    }
    for node in body.iter(word_text, math_text):
        if not (node.text or '').strip():
            continue
        tag = node.tag
        for parent in node.iterancestors():
            if parent.tag not in allowed_parents.get(tag, ()):
                raise DocumentReadError('docx_unsupported_structure')
            if parent is body:
                break
            tag = parent.tag


def _docx_text(container) -> tuple[str, bool]:
    from docx.oxml.text.paragraph import CT_P

    parts = []
    has_text = False
    for block in container.inner_content_elements:
        if isinstance(block, CT_P):
            text = block.text
            parts.append(text)
            has_text = has_text or bool(text.strip())
        else:
            # Use actual cells in file order; grid cells can repeat a merged cell.
            for row in block.tr_lst:
                cells = [_docx_text(cell) for cell in row.tc_lst]
                parts.append(' | '.join(text for text, _ in cells))
                has_text = has_text or any(cell_has_text for _, cell_has_text in cells)
    return '\n'.join(parts), has_text


def _read_docx(stream) -> str:
    from docx import Document

    with ZipFile(stream) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > MAX_DOCX_EXPANDED_BYTES:
            raise DocumentReadError('document_expansion_limit')
    stream.seek(0)
    document = Document(stream)
    _check_docx_structure(document)
    text, has_text = _docx_text(document.element.body)
    return text if has_text else ''


def read_document(path: Path) -> str:
    """Read supported local text or fail with a safe DocumentReadError."""
    protect_dependency_logs()
    suffix = path.suffix.lower()
    try:
        metadata = path.stat(follow_symlinks=False)
        if S_ISLNK(metadata.st_mode):
            raise DocumentReadError('input_symlink')
        if not S_ISREG(metadata.st_mode):
            raise DocumentReadError('input_invalid')
        if suffix not in {'.txt', '.md', '.pdf', '.docx'}:
            raise DocumentReadError('input_unsupported')
        if not metadata.st_size:
            raise DocumentReadError('document_empty')
        if metadata.st_size > MAX_BYTES:
            raise DocumentReadError('input_too_large')

        with path.open('rb') as stream:
            contents = stream.read(MAX_BYTES + 1)
        if len(contents) > MAX_BYTES:
            raise DocumentReadError('input_too_large')
        if not contents:
            raise DocumentReadError('document_empty')

        if suffix == '.pdf':
            text = _read_pdf(BytesIO(contents))
        elif suffix == '.docx':
            text = _read_docx(BytesIO(contents))
        else:
            try:
                text = contents.decode('utf-8-sig')
            except UnicodeDecodeError:
                raise DocumentReadError('document_encoding_invalid') from None
    except DocumentReadError:
        raise
    except (FileNotFoundError, NotADirectoryError):
        raise DocumentReadError('input_invalid') from None
    except PermissionError:
        raise DocumentReadError('input_access_denied') from None
    except ImportError:
        raise DocumentReadError('parser_dependency_missing') from None
    except Exception:
        raise DocumentReadError('document_unreadable') from None

    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        raise DocumentReadError('document_empty')
    if len(text) > MAX_CHARS:
        raise DocumentReadError('document_text_too_long')
    if '\x00' in text:
        raise DocumentReadError('document_text_invalid')
    return text


def inspect_documents(paths: Iterable[Path]) -> list[dict[str, str | int]]:
    """Return one result per file in input order, using only its position."""
    results = []
    for position, path in enumerate(paths, start=1):
        try:
            characters = len(read_document(path))
        except DocumentReadError as error:
            results.append({'file': position, 'status': 'error', **document_diagnostic(error)})
        else:
            results.append({'file': position, 'status': 'ok', 'characters': characters})
    return results


def _main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Локальная проверка файлов перед анализом.', allow_abbrev=False)
    parser.add_argument('files', type=Path, nargs='+', metavar='ФАЙЛ')
    args, unknown = parser.parse_known_args()
    if unknown:
        parser.error('Укажите пути к файлам после --.')
    results = inspect_documents(args.files)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 2 if any(result['status'] == 'error' for result in results) else 0


if __name__ == '__main__':
    raise SystemExit(_main())
