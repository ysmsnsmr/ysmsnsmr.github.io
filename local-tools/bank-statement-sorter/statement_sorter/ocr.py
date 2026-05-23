from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile


class OcrError(RuntimeError):
    pass


def ocr_pdf(path: str | Path, language: str = "eng", dpi: int = 250) -> str:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise OcrError(f"PDF not found: {pdf_path}")
    if shutil.which("tesseract") is None:
        raise OcrError("tesseract is not installed. Install it with: brew install tesseract")

    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise OcrError(
            "PyMuPDF is not installed. Run: pip install -r requirements.txt"
        ) from exc

    page_texts: list[str] = []
    scale = dpi / 72
    matrix = fitz.Matrix(scale, scale)

    with fitz.open(pdf_path) as document, tempfile.TemporaryDirectory() as tmp_dir:
        for index, page in enumerate(document, start=1):
            image_path = Path(tmp_dir) / f"page-{index:04d}.png"
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pixmap.save(image_path)
            page_texts.append(_ocr_image(image_path, language=language, page_number=index))

    return "\n\n".join(page_texts)


def _ocr_image(path: Path, language: str, page_number: int) -> str:
    command = ["tesseract", str(path), "stdout", "-l", language, "--psm", "6"]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        details = completed.stderr.strip() or "unknown OCR error"
        raise OcrError(f"tesseract failed on page {page_number}: {details}")
    return completed.stdout
