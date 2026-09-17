import os
import io
import re
import logging
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)

_ocr_engine = None

def get_ocr_engine():
    """
    Lazily initializes and returns the RapidOCR (PP-OCR ONNX) engine.
    Returns None if RapidOCR or onnxruntime is not available.
    """
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
            logger.info("Initialized local PP-OCR engine (RapidOCR ONNX).")
        except Exception as e:
            logger.warning(f"Could not initialize RapidOCR: {e}")
            _ocr_engine = False
    return _ocr_engine if _ocr_engine is not False else None

def extract_text_from_pixmap(pix) -> str:
    """
    Runs local PP-OCR on a PyMuPDF pixmap and returns joined text lines.
    """
    engine = get_ocr_engine()
    if engine is None:
        return ""
    try:
        img_bytes = pix.tobytes("png")
        res, _ = engine(img_bytes)
        if res:
            lines = [item[1].strip() for item in res if item and len(item) > 1 and item[1].strip()]
            return '\n'.join(lines)
    except Exception as e:
        logger.warning(f"Error during local PP-OCR on pixmap: {e}")
    return ""

def is_garbled_or_poor_ocr(text: str) -> bool:
    """
    Detects if extracted digital text layer is corrupted, fragmented, or garbled scanner OCR.
    Common symptoms:
    - Contains Unicode replacement characters \ufffd
    - Excessive single-character lines (indicates vertical scanner artifacts or broken text layer)
    - Low density of valid alphanumeric characters
    """
    if not text or not text.strip():
        return True

    clean = text.strip()

    # 1. Unicode replacement character check (\ufffd)
    replacement_count = clean.count('\ufffd')
    if replacement_count >= 2:
        return True
    if replacement_count > 0 and (replacement_count / len(clean)) > 0.005:
        return True

    # 2. Line fragmentation check (many 1-2 char lines)
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if len(lines) >= 4:
        tiny_lines = sum(1 for line in lines if len(line) <= 2)
        if tiny_lines / len(lines) > 0.25:
            return True

    # 3. Alphanumeric density check
    alnum_count = sum(1 for ch in clean if ch.isalnum())
    if len(clean) > 20 and (alnum_count / len(clean)) < 0.40:
        return True

    return False

def extract_pdf_pages_text(
    pdf_path: str,
    max_pages: int = 3,
    min_char_threshold: int = 30,
    force_ocr: bool = False
) -> Tuple[str, str]:
    """
    Extracts text from a PDF file.
    First checks for native digital text layer via PyMuPDF.
    If digital text is absent, sparse (< min_char_threshold characters), or garbled/corrupted OCR,
    automatically executes local PP-OCR (RapidOCR) on Page 1 and the signature page.

    Returns:
        Tuple[str, str]: (text_page_1, text_full)
    """
    text_p1 = ""
    text_full = ""
    try:
        import fitz
        with fitz.open(pdf_path) as doc:
            total_pages = len(doc)
            if total_pages == 0:
                return "", ""

            # 1. Attempt digital text extraction
            text_p1 = doc[0].get_text()
            pages_text = [doc[i].get_text() for i in range(min(total_pages, max_pages))]
            text_full = '\n'.join(pages_text)

            # 2. Check if digital text is clean and sufficient
            p1_garbled = is_garbled_or_poor_ocr(text_p1)
            if not force_ocr and len(text_p1.strip()) >= min_char_threshold and not p1_garbled:
                logger.debug(f"Extracted clean digital text layer from {pdf_path} ({len(text_p1.strip())} chars on P1).")
                return text_p1, text_full

            reason = "force_ocr requested" if force_ocr else ("garbled/corrupted scanner text layer" if p1_garbled else f"sparse text ({len(text_p1.strip())} chars)")
            logger.info(f"Digital text layer issue ({reason}). Executing local PP-OCR on '{os.path.basename(pdf_path)}'...")

            # 3. Scanned PDF / Corrupted text: Run local PP-OCR (RapidOCR)
            pix_p1 = doc[0].get_pixmap(dpi=200)
            ocr_p1 = extract_text_from_pixmap(pix_p1)
            ocr_pages = [ocr_p1] if ocr_p1 else []

            # If multi-page, also OCR the signature/notarial page (last page or page 2)
            if total_pages > 1:
                last_page_idx = total_pages - 1
                if last_page_idx != 0:
                    pix_last = doc[last_page_idx].get_pixmap(dpi=200)
                    ocr_last = extract_text_from_pixmap(pix_last)
                    if ocr_last:
                        ocr_pages.append(ocr_last)

            # If OCR yielded text, prefer it over garbled digital text
            if ocr_p1 and ocr_p1.strip():
                text_p1 = ocr_p1
                text_full = '\n'.join(ocr_pages)
                logger.info(f"Local PP-OCR completed for '{os.path.basename(pdf_path)}': {len(text_p1)} chars on P1, {len(text_full)} chars total.")
            elif not text_p1.strip() and ocr_p1:
                text_p1 = ocr_p1
                text_full = '\n'.join(ocr_pages)

    except Exception as e:
        logger.error(f"Error extracting text from PDF '{pdf_path}': {e}", exc_info=True)

    return text_p1, text_full
