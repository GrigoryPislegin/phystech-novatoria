from pathlib import Path
from zipfile import ZipFile

MAX_BYTES = 5_000_000
MAX_CHARS = 60_000


def read_document(path: Path) -> str:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('document_size_or_missing')
    suffix = path.suffix.lower()
    try:
        if suffix in ('.txt', '.md'):
            text = path.read_text(encoding='utf-8-sig')
        elif suffix == '.pdf':
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                if len(pdf.pages) > 100:
                    raise ValueError('too_many_pages')
                parts = [p.extract_text() or '' for p in pdf.pages]
                if any(not p.strip() for p in parts):
                    raise ValueError('ocr_required_or_empty_page')
                text = '\n\n'.join(parts)
        elif suffix == '.docx':
            from docx import Document
            with ZipFile(path) as archive:
                if sum(x.file_size for x in archive.infolist()) > 20_000_000:
                    raise ValueError('document_expansion_limit')
            try:
                document = Document(path)
            except ValueError:
                raise ValueError('document_unreadable') from None
            parts = []
            has_text = False
            for block in document.iter_inner_content():
                if hasattr(block, 'rows'):
                    for row in block.rows:
                        cells = [cell.text for cell in row.cells]
                        has_text = has_text or any(cell.strip() for cell in cells)
                        parts.append(' | '.join(cells))
                else:
                    paragraph = block.text
                    has_text = has_text or bool(paragraph.strip())
                    parts.append(paragraph)
            text = '\n'.join(parts) if has_text else ''
        else:
            raise ValueError('unsupported_format')
    except ImportError:
        raise ValueError('parser_dependency_missing') from None
    except ValueError:
        raise
    except Exception:
        raise ValueError('document_unreadable') from None
    text = text.replace('\r\n', '\n').strip()
    if not text or len(text) > MAX_CHARS or '\x00' in text:
        raise ValueError('empty_or_oversized_text')
    return text
