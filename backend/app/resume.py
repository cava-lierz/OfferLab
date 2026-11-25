from io import BytesIO
from pathlib import Path
from .store import AppError

MAX_BYTES = 5 * 1024 * 1024


def extract_resume(filename, content):
    if not content or len(content) > MAX_BYTES:
        raise AppError('文件不能为空，且不能超过 5 MB')
    suffix = Path(filename or '').suffix.lower()
    if suffix == '.txt':
        try:
            result = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise AppError('TXT 请使用 UTF-8 编码，或直接粘贴文本') from None
    elif suffix == '.pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 20:
                raise AppError('请上传未加密且不超过 20 页的 PDF')
            chunks = []
            for page in reader.pages:
                chunks.append(page.extract_text() or '')
                if sum(map(len, chunks)) > 20000:
                    raise AppError('解析文本超过 20000 字，请精简简历')
            result = '\n'.join(chunks)
        except AppError:
            raise
        except Exception:
            raise AppError('PDF 无法解析，请重新导出或粘贴文本') from None
    else:
        raise AppError('仅支持文本型 PDF 和 UTF-8 TXT')
    result = result.replace('\x00', '').strip()
    if len(result) < 20:
        raise AppError('提取的文本太少；扫描版 PDF 请先 OCR，或直接粘贴简历')
    if len(result) > 20000:
        raise AppError('解析文本超过 20000 字，请精简简历')
    return result
