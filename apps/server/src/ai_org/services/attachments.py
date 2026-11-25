"""첨부 파일 검증·저장.

Claude Code에는 파일 내용을 직접 넣지 않고, 저장 경로를 add_dirs로 허용한 뒤 프롬프트에 경로를 알린다.
Claude Code의 Read 도구는 텍스트·이미지(PNG/JPEG/GIF/WebP)·PDF를 읽을 수 있다(공식 도구 문서).
"""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES_PER_MESSAGE = 10

IMAGE_TYPES = {
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".gif": ("image/gif", b"GIF8"),
    ".webp": ("image/webp", b"RIFF"),
}
PDF = (".pdf", "application/pdf", b"%PDF-")
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".xml",
    ".html",
    ".css",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".sh",
    ".sql",
    ".log",
    ".diff",
    ".patch",
}


class AttachmentError(ValueError):
    pass


@dataclass(frozen=True)
class Checked:
    filename: str
    media_type: str


def safe_name(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().lstrip(".")
    base = re.sub(r"[^\w.\- ()가-힣]", "_", base)
    return base[:120] or "file"


def check(filename: str, head: bytes) -> Checked:
    """확장자와 파일 앞부분(매직 바이트)이 일치하는지 확인한다."""
    name = safe_name(filename)
    ext = Path(name).suffix.lower()
    if ext in IMAGE_TYPES:
        media, magic = IMAGE_TYPES[ext]
        if not head.startswith(magic) or (ext == ".webp" and head[8:12] != b"WEBP"):
            raise AttachmentError("이미지 형식이 확장자와 맞지 않습니다.")
        return Checked(name, media)
    if ext == PDF[0]:
        if not head.startswith(PDF[2]):
            raise AttachmentError("PDF 형식이 아닙니다.")
        return Checked(name, PDF[1])
    if ext in TEXT_EXTENSIONS:
        if b"\x00" in head:
            raise AttachmentError("텍스트 파일이 아닙니다.")
        try:
            head.decode("utf-8")
        except UnicodeDecodeError as exc:
            # 경계에서 잘린 멀티바이트 문자는 허용한다.
            if exc.start < len(head) - 4:
                raise AttachmentError("UTF-8 텍스트가 아닙니다.") from exc
        return Checked(name, "text/plain")
    raise AttachmentError(f"지원하지 않는 파일 형식입니다: {ext or '(확장자 없음)'}")


def store(
    upload_root: Path, attachment_id: str, checked: Checked, chunks: list[bytes]
) -> tuple[Path, int, str]:
    folder = upload_root / attachment_id
    folder.mkdir(parents=True, mode=0o700)
    target = folder / checked.filename
    digest = hashlib.sha256()
    size = 0
    with target.open("xb") as fh:
        for chunk in chunks:
            size += len(chunk)
            digest.update(chunk)
            fh.write(chunk)
    target.chmod(0o600)
    return target, size, digest.hexdigest()


def remove(stored_path: str, upload_root: Path) -> None:
    folder = Path(stored_path).parent
    if folder.parent == upload_root and folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
