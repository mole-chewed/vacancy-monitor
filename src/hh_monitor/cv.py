from __future__ import annotations

from pathlib import Path

try:  # pragma: no cover - optional dependency path
    from pypdf import PdfReader
except ModuleNotFoundError:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment]


class CvExtractionError(RuntimeError):
    """Raised when the CV PDF cannot be read or extracted."""


def extract_cv_text(pdf_path: str | Path, max_chars: int = 40000) -> str:
    path = Path(pdf_path)
    if not path.exists():
        raise CvExtractionError(f"CV file not found: {path}")
    if PdfReader is None:
        raise CvExtractionError("pypdf is not installed. Install dependencies before using CV-based reporting.")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pragma: no cover - depends on PDF parser/runtime
        raise CvExtractionError(f"Failed to open CV PDF: {exc}") from exc

    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pragma: no cover - depends on PDF parser/runtime
            raise CvExtractionError(f"Failed to extract text from CV PDF: {exc}") from exc
        if text.strip():
            parts.append(text.strip())

    merged = "\n\n".join(parts).strip()
    if not merged:
        raise CvExtractionError(f"No text extracted from CV PDF: {path}")
    return merged[:max_chars]
