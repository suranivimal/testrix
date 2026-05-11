from pathlib import Path


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def read_requirements_file(path: str) -> str:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install pypdf to parse PDF requirement files.") from exc
        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install python-docx to parse DOCX requirement files.") from exc
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)

    raise ValueError(f"Unsupported requirements file type: {suffix}")
