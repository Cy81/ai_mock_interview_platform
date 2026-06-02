"""简历解析：MIME 嗅探 + PDF / DOCX / 文本 多格式 + 异步友好。

设计要点：
- 用 python-magic 嗅探真实 MIME，不只信扩展名（防伪造）；
- 文件大小、MIME 白名单在写入前强校验，杜绝 RCE / 解析炸弹；
- 解析逻辑独立成 `extract_text`，可以被 Celery 任务复用；
- 新建 Resume 时立刻入库（status=PARSING），LLM 解析失败也保留原文。
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Optional

import structlog
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import DomainError
from app.models.resume import Resume, ResumeParseStatus
from app.models.user import User
from app.services.ai_provider import get_ai_provider


logger = structlog.get_logger("resume.parser")


SUPPORTED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/octet-stream",  # 部分浏览器对 .md 用此 MIME
}


# =====================================================================
# 入口
# =====================================================================


async def create_resume_from_upload(
    db: Session,
    user: User,
    upload: UploadFile,
    target_position: str | None = None,
) -> Resume:
    filename = (upload.filename or "resume.txt").strip() or "resume.txt"
    content = await upload.read()
    max_bytes = settings.MAX_RESUME_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise DomainError(f"简历文件不能超过 {settings.MAX_RESUME_UPLOAD_MB}MB", 413)
    mime_type = _detect_mime(content, filename)
    if mime_type not in SUPPORTED_MIMES:
        raise DomainError(f"不支持的文件类型：{mime_type}", 415)
    text = extract_text(content, mime_type=mime_type, filename=filename)
    return create_resume_from_text(
        db,
        user,
        filename=filename,
        text=text,
        mime_type=mime_type,
        file_size=len(content),
        content_hash=_sha256(content),
        target_position=target_position,
    )


def create_resume_from_text(
    db: Session,
    user: User,
    *,
    filename: str,
    text: str,
    mime_type: str | None = None,
    file_size: int = 0,
    content_hash: str | None = None,
    target_position: str | None = None,
) -> Resume:
    clean_text = (text or "").strip()
    if len(clean_text) < 20:
        raise DomainError("简历内容过短，请至少提供 20 个字符")

    resume = Resume(
        user_id=user.id,
        filename=filename[:255],
        mime_type=mime_type,
        file_size=file_size or len(clean_text.encode("utf-8")),
        content_hash=content_hash or _sha256(clean_text.encode("utf-8")),
        raw_text=clean_text,
        parsed_profile={},
        target_position=(target_position or "").strip()[:120] or None,
        parse_status=ResumeParseStatus.PARSING,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    try:
        profile, meta = get_ai_provider().parse_resume(clean_text)
        resume.parsed_profile = profile or {}
        resume.parse_status = ResumeParseStatus.PARSED
        logger.info(
            "resume_parsed",
            resume_id=resume.id,
            ai_latency_ms=meta.latency_ms,
            ai_tokens=meta.usage.total_tokens,
        )
    except Exception as exc:
        resume.parse_status = ResumeParseStatus.FAILED
        resume.parse_error = str(exc)[:1000]
        logger.exception("resume_parse_failed", resume_id=resume.id)
    db.commit()
    db.refresh(resume)
    return resume


# =====================================================================
# 文件内容提取
# =====================================================================


def extract_text(
    content: bytes,
    *,
    mime_type: str | None = None,
    filename: str | None = None,
) -> str:
    if not mime_type:
        mime_type = _detect_mime(content, filename or "")
    if mime_type == "application/pdf":
        return _extract_pdf(content)
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(content)
    if mime_type in ("text/plain", "text/markdown", "text/x-markdown", "application/octet-stream"):
        return content.decode("utf-8", errors="ignore")
    raise DomainError(f"不支持的文件类型：{mime_type}", 415)


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        logger.exception("pdf_extract_failed")
        raise DomainError("PDF 解析失败，请检查文件是否损坏或为扫描件")


def _extract_docx(content: bytes) -> str:
    try:
        from docx import Document

        document = Document(BytesIO(content))
        return "\n".join(p.text for p in document.paragraphs if p.text)
    except Exception:
        logger.exception("docx_extract_failed")
        raise DomainError("DOCX 解析失败，请检查文件是否损坏")


def _detect_mime(content: bytes, filename: str) -> str:
    """优先用 python-magic 嗅探真实类型，失败则回落到扩展名。"""
    try:
        import magic  # type: ignore

        sniff = magic.from_buffer(content[:4096], mime=True)
        if sniff:
            return sniff
    except Exception:  # pragma: no cover
        pass
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "md": "text/markdown",
    }.get(suffix, "application/octet-stream")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
