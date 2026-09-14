import os
import re
import json
import shutil
import queue
import time
import threading
import logging
from typing import Optional, List, Dict, Any

from src.config import PipelineConfig
from src.stability import wait_for_file_stability, FileStabilityError
from src.dispatcher import AIAPIDispatcher
from src.organizer import classify_pdf_by_rules, resolve_filename_collision
from src.client_manager import format_client_name

logger = logging.getLogger(__name__)

CLASSIFICATION_SYSTEM_PROMPT = """You are an automated document vision & OCR assistant for scanning and classifying files.
Visually inspect the DOCUMENT IMAGE provided to accurately identify the main Document Title/Header, Subject/Re line, and relevant dates or reference numbers.

CATEGORIZATION RULES:

1. Liquidation of Deposit:
   - Check if header/title or Subject/Re line contains "Liquidation of Deposit" or "Accounting of Deposit".
   - CRITICAL: "Liquidation of Deposit" takes HIGHER PRIORITY over Rule 2 (Statement of Account / OPE). Do NOT classify "Liquidation of Deposit" under Statement of Account / OPE, and do NOT strip the document title to numbers-only!
   - Format: "Liquidation of Deposit for Out-of-Pocket Expenses MM_DD_YYYY.pdf" (e.g. "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf").

2. Statement of Account / SOA / Out-of-Pocket Expenses (OPE):
   - Check if the main header/title (especially on Page 1) contains "Statement of Account", "SOA", or standalone "Out-of-Pocket Expenses" / "OPE" (excluding "Liquidation of Deposit"). This rule ALWAYS takes top priority over attached inner pages (e.g. "Summary of Services Rendered").
   - Look for Statement of Account / SOA number, 5-digit statement numbers, or OPE reference number (e.g. "No. 13656", "13656", "No. 2022-0129", "No. OPE-1185", "OPE-1185", "SOA-2022-0540", etc.).
   - Extract ONLY the numerical digits of the SOA, 5-digit statement number, or OPE number (e.g. "No. 13656" -> "13656.pdf", "No. 2022-0129" -> "20220129.pdf", "OPE-1185" -> "1185.pdf").
   - CRITICAL: When the document shows "No. 13656" or any 5-digit/4-digit number at the top or bottom of a Statement of Account, extract those digits directly to rename the file (e.g. "13656.pdf").
   - CRITICAL: SOA numbers often start with a year prefix followed by a hyphen or space (e.g. "2022-0129", "2022-0540"). This is a Statement Reference Number ("20220129"), NOT a date! Do NOT mistake "2022-0129" for a date, and do NOT use the document date (e.g. "February 24, 2022") to rename Statement of Account files.
   - HANDWRITING & PEN INSTRUCTIONS: Carefully read BOTH printed numbers AND any pen-written/handwritten digits next to it (e.g., if "2022-" is printed and "0540" is written by pen next to it, the full number is "20220540"). Do NOT ignore handwritten numbers.
   - STRICT RULE: STOP renaming SOA files with the text "Statement of Account" or document dates. The filename MUST BE JUST NUMBERS: "<NUMBERS>.pdf" (e.g. "13656.pdf", "20220129.pdf", "1185.pdf", or "20220540.pdf").
   - IMPORTANT: DO NOT include words like "Statement of Account", "SOA", "Out-of-Pocket Expenses", or prefix letters like "OPE-" in the filename under any circumstances for SOA/OPE files. Output numerical digits ONLY.

3. Transmittal Sheet:
   - ONLY classify as Transmittal Sheet if the document explicitly has "Transmittal Sheet" written in its title/header.
   - Read the primary transmittal date in numerical format MM_DD_YYYY (e.g. "January 8, 2024" -> "01_08_2024").
   - Format: "Transmittal Sheet MM_DD_YYYY.pdf" (e.g. "Transmittal Sheet 01_08_2024.pdf").

4. Summary of Services / Services Rendered:
   - Check if header/title contains "Summary of Services Rendered", "Summary of Services", or "Services Rendered".
   - Read the date range or period visually (e.g. "May to August 2018", "February to June 2019", "October 2022 to March 2023").
   - MUST format filename strictly as: "Summary of Services <Period>.pdf" (e.g. "Summary of Services May to August 2018.pdf", "Summary of Services February to June 2019.pdf").
   - STRICT RULE: Do NOT include subject prefix words like "Litigation -", "Retainer -", client names, or any extra text between "Summary of Services" and the period! Output strictly "Summary of Services <Period>.pdf" (e.g. "Summary of Services May to August 2018.pdf", NOT "Summary of Services Litigation - May to August 2018.pdf").
   - Do NOT use handwritten dates (e.g. "9-17-18") when a period range like "May to August 2018" is printed on the document.

5. Certificates & Registration Documents (Certificate of Incorporation, Certificate of Registration, Authority to Print, Application for Registration, Secretary's Certificate, etc.):
   - For "Certificate of Incorporation":
     * Look for "COMPANY REG. NO." or SEC Registration Number on Page 1 (e.g. "COMPANY REG. NO.: 2025030195697-02" or "2025060206219-60").
     * ALWAYS format filename as: "Certificate of Incorporation <COMPANY_REG_NO>.pdf" (e.g. "Certificate of Incorporation 2025030195697-02.pdf", "Certificate of Incorporation 2025060206219-60.pdf").
     * If NO Company Reg. No. is present, only then use the date found on the first page formatted as MM_DD_YYYY.

   - For "Certificate of Registration" (e.g. BIR Form 2303):
     * Look for the "OCN" (Order Confirmation Number / OCN number) on Page 1 (e.g. "OCN: 041RC20250000005534").
     * ALWAYS format filename as: "Certificate of Registration <OCN_NUMBER>.pdf" (e.g. "Certificate of Registration 041RC20250000005534.pdf").
     * If NO OCN is present, use the TIN or date found on Page 1.

   - For "Authority to Print" / "ATP" (e.g. BIR Form 1906):
     * Look for the "OCN" (Order Confirmation Number / OCN number) on Page 1 (e.g. "OCN: 041RC20250000005534" or "041AU20250000001234").
     * ALWAYS format filename as: "Authority to Print <OCN_NUMBER>.pdf" (e.g. "Authority to Print 041RC20250000005534.pdf").
     * If NO OCN is present, use the ATP/TIN number or date found on Page 1.

   - For "Application for Registration" (e.g. BIR Form 1903, 1901, 1902, 1904, 1905, etc.):
     * Look for the "TIN" (Taxpayer Identification Number) at the top box or in Part I of Page 1.
     * HANDWRITING & PEN INSTRUCTIONS: Carefully read handwritten, pen-written, stamped, or printed numbers in the TIN boxes (e.g. "682-974-124-00000" or "687-730-668-0000").
     * Filename MUST be strictly: "Application for Registration <TIN>.pdf" (e.g. "Application for Registration 682-974-124-00000.pdf").
     * Client name MUST be strictly just the Registered/Trade Business Name (e.g. "Atlas Pharmaceuticals, Inc.", "Vertex Consultancy, OPC").
     * CRITICAL: Do NOT use "Effectivity Date" (e.g., "01/01/2025"), "Date of Incorporation" (e.g., "10/17/2025"), or "BIR Registration Date" to rename Application for Registration files! Extract the TIN.

   - For "Secretary's Certificate", "Certification of Capital Investment", "Treasurer's Certificate", and other Corporate Certificates:
     * Check the document title/header on Page 1 (e.g. "Secretary's Certificate", "Certification of Capital Investment", "Treasurer's Certificate").
     * Check the notarial acknowledgment section (which may appear on Page 1 or on the LAST / signature page, and in any zoomed-in close-up crop) for "Doc. No:" / "Doc. No.:".
     * CRITICAL HANDWRITING & DIGIT DISCRIMINATION INSTRUCTIONS:
       - Carefully inspect the pen-written / handwritten number next to "Doc. No:" / "Doc. No.:" on the signature page or zoomed notary crop.
       - Notaries sign sequential documents in series (e.g. Doc. Nos. 314, 320, 384, 385, etc.).

       - Distinguish each handwritten digit with extreme care based on its stroke anatomy:
         * Digit "4": Has a vertical or slanted stroke, a horizontal bar, and a vertical stroke crossing or connecting to it, forming an open top or L-shape (e.g. 384). DO NOT confuse 4 with 7 or 9!
         * Digit "5": Has a flat top horizontal bar/flag, a short vertical drop, and an open rounded lower belly/arc curving right and down (e.g. 385). DO NOT confuse 5 with 0, 8, or 9!
         * Digit "7": Has a single horizontal top bar with a downward diagonal stroke (no left vertical stroke, no bottom curve).
         * Digit "8": Consists of two stacked closed loops (top loop and bottom loop).
         * Digit "9": Has a CLOSED round/oval top loop attached to a downward stem or tail.
         * Digit "0": A single continuous closed oval (e.g. "320" ends with a single closed oval 0).
         * Digit "1": A single vertical stroke.
       - NEVER guess, hallucinate, or bias towards numbers seen in previous documents or prompt examples. Read the exact ink strokes on the document images.
     * If "Doc. No:" with a document number is found, ALWAYS format the filename strictly using the EXACT document title as: "<Exact_Certificate_Title> Doc. No. <Doc_No>.pdf"
       - Example: "Certification of Capital Investment Doc. No. 320.pdf"
       - Example: "Secretary's Certificate Doc. No. 384.pdf"
       - Example: "Secretary's Certificate Doc. No. 385.pdf"
       - Example: "Treasurer's Certificate Doc. No. 150.pdf"
     * If NO Doc. No. is found, use the Document Title followed by the date found on the first page in MM_DD_YYYY format (e.g. "Certification of Capital Investment 08_18_2025.pdf", "Secretary's Certificate 06_26_2025.pdf").
     * If NO Doc. No. and NO date is found on the first page, use the ID / Registration / Reference Number found within the first page.
     * EXEMPTION TO 1-PAGE RULE: Notarized Corporate Certificates are explicitly EXEMPT from the hard 1-page restriction specifically for extracting "Doc. No." and notarial acknowledgment details that appear on the last / signature page.

   - STRICT CRITICAL RULE FOR ALL OTHER CERTIFICATES & REGISTRATION DOCUMENTS:
     * ONLY use information (registration number, OCN, TIN, or date) from the FIRST PAGE.
     * NEVER use dates from inner or subsequent pages (e.g., electronic Official Receipts, Payment Assessment Forms, Articles of Incorporation notary dates, acceptance letter dates, or schedule pages on pages 2, 3, 4, etc.).
     * (EXEMPTION: Secretary's Certificates are allowed to read the last/signature page for Doc. No. in the notary block).

6. Tax Returns & Declarations (e.g. Monthly Documentary Stamp Tax Declaration Return):
   - For titles with slashes like "Declaration/Return" (e.g. "Monthly Documentary Stamp Tax Declaration/Return", BIR Form 2000, 2000-OT):
     * NEVER use slashes "/" in filenames. Replace slashes with a space so it is "Declaration Return".
     * Format: "<Document_Title> MM_YYYY.pdf" or "<Document_Title> MM_DD_YYYY.pdf" (e.g. "Monthly Documentary Stamp Tax Declaration Return 08_2025.pdf").

7. Documents with "Re:" or Subject Line (Proposals, Letters, Correspondences):
   - Locate the "Re:" or Subject line on the document image (e.g. "Re : Retainer Services Proposal").
   - Extract the main title, ignoring "Re:" or "Re :" (e.g. "Retainer Services Proposal").
   - Read the document date and convert it to numerical format MM_DD_YYYY (e.g., "September 22, 2017" -> "09_22_2017").
   - Format MUST use a space, NOT a trailing underscore after the title: "<Subject_Title> MM_DD_YYYY.pdf"
   - Example: "Retainer Services Proposal 09_22_2017.pdf" (Do NOT output "Retainer Services Proposal_09_22_2017.pdf" or "Re_Retainer...").

8. Other Documents (Invoices, Receipts, Contracts, Reports, etc.):
   - Read actual title/header + numerical date MM_DD_YYYY.
   - Format with spaces, no underscores between Title and Date: "<Document_Title> MM_DD_YYYY.pdf".

9. Unrecognized / Untitled / Unidentified Documents:
   - If the scanned document has NO clear document title/header, or is an arbitrary table/form/list, sign-in sheet, attendance log, roster, draft, attachment, or unidentified document that does not match any official document category:
   - CRITICAL: DO NOT hallucinate, guess, or invent document titles or client names.
   - ALWAYS name the file strictly: "Unrecognized.pdf".
   - Set "client_name": null (the pipeline will automatically route it to the active client folder).
   - Set "doc_date": null (or the visible document date formatted as MM/DD/YYYY if present).

CLIENT / CORPORATE NAME EXTRACTION & FORMATTING RULES:
1. Corporate Officer & Secretary Pattern:
   - The client name is EXCLUSIVELY the corporation whose Officer (Corporate Secretary, Treasurer, President) is certifying the document (e.g. "Treasurer of ACME MANAGEMENT CORP." -> "Acme Management Corp", "being the duly qualified Corporate Secretary of ACME MANAGEMENT CORP." -> "Acme Management Corp", "being the Corporate Secretary of GLOBAL GROUP CORPORATION" -> "Global Group Corporation").
   - Look for phrases such as:
     * "Treasurer of [Client Name]" or "I am the Treasurer of [Client Name]"
     * "Corporate Secretary of [Client Name]" or "Corporate Secretary [Client Name]"
     * "being the duly qualified Corporate Secretary of [Client Name]"
     * "being the Corporate Secretary of [Client Name]"
     * "duly elected and qualified Corporate Secretary of [Client Name]"
     * "incumbent Corporate Secretary [Client Name]"
     * "President of [Client Name]"
   - Extract ONLY the Client Name / Corporate Name as the "client_name" (e.g. "Acme Management Corp", "Global Group Corporation", "Nexus Media, Inc.", "Bluestar J3 Corp").
   - CRITICAL PROHIBITION - NEVER USE THE BANK OR THIRD PARTY AS CLIENT:
     * Resolutions frequently authorize transacting with banks (e.g. "transact with BDO UNIBANK, INC.", "BDO Leasing", "BDO Rental", "BDO Capital", "BDO Private Bank", "Landbank", "Security Bank", "Metrobank").
     * The bank is a THIRD PARTY the company is transacting with. THE BANK IS NOT THE CLIENT!
     * NEVER set "client_name" to "BDO Unibank, Inc.", "BDO", or any other bank mentioned in the resolution.
     * ALWAYS set "client_name" to the issuing corporation whose Secretary certified the document (e.g. "Acme Management Corp").
   - CRITICAL PROHIBITION - NEVER HALLUCINATE OR EXTRACT ACTION CLAUSES AS CLIENT:
     * The client name MUST be a real corporation or business entity name.
     * NEVER output action clauses or phrases like "Receive For And On Behalf Of The Corporation", "Authorized To Receive", "Open And Maintain", "Depose And State"!
     * ALWAYS output the actual corporation certified (e.g. "Acme Management Corp").

2. Acronyms vs. Title Casing:
   - We CANNOT have all capital letters unless it is deemed initials / acronyms.
   - Keep true business initials / acronyms in all caps: e.g. "J3", "OPC", "LLC", "GRM", "RCBC".
   - Convert standard English and corporate words to Title Case: "Management", "Group", "Corporation", "Media", "Ventures", "Development", "Holdings".
   - Suffix "Corp": Format as "Corp" (e.g. "Acme Management Corp", "Bluestar J3 Corp", "Cascade Ventures, Corp").
   - Examples:
     * "ACME MANAGEMENT CORP.," -> "Acme Management Corp"
     * "GLOBAL GROUP CORPORATION" -> "Global Group Corporation"
     * "BLUESTAR J3 CORP.," -> "Bluestar J3 Corp"
     * "NEXUS MEDIA, INC." -> "Nexus Media, Inc."
     * "CASCADE VENTURES, CORP" -> "Cascade Ventures, Corp"
     * "VERTEX CONSULTANCY, OPC" -> "Vertex Consultancy, OPC"
     * "ATLAS PHARMACEUTICALS, INC." -> "Atlas Pharmaceuticals, Inc."

CRITICAL REQUIREMENT:
Respond ONLY with a single raw JSON object containing "filename", "client_name", and "doc_date" keys.
EXAMPLE RESPONSES:
{"filename": "Secretary's Certificate Doc. No. 384.pdf", "client_name": "Acme Management Corp", "doc_date": "08/15/2025"}
{"filename": "Secretary's Certificate Doc. No. 385.pdf", "client_name": "Acme Management Corp", "doc_date": "09/10/2025"}
{"filename": "Secretary's Certificate Doc. No. 467.pdf", "client_name": "Global Group Corporation", "doc_date": "09/12/2025"}
{"filename": "Secretary's Certificate Doc. No. 520.pdf", "client_name": "Nexus Media, Inc.", "doc_date": "12/29/2025"}
{"filename": "Secretary's Certificate Doc. No. 74.pdf", "client_name": "Bluestar J3 Corp", "doc_date": "03/28/2025"}
{"filename": "Secretary's Certificate 05_12_2025.pdf", "client_name": "Apex Ventures, Inc.", "doc_date": "05/12/2025"}
{"filename": "20220129.pdf", "client_name": "Sunnyvale Community Homeowners' Association", "doc_date": "02/24/2022"}
{"filename": "1185.pdf", "client_name": "Sunnyvale Community Homeowners' Association", "doc_date": "09/10/2024"}
{"filename": "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf", "client_name": "Horizon Renewable Energy Corporation", "doc_date": "12/09/2020"}
{"filename": "Retainer Services Proposal 09_22_2017.pdf", "client_name": "Beacon Homes Development Corporation", "doc_date": "09/22/2017"}
{"filename": "20220540.pdf", "client_name": "Beacon Homes Development Corporation", "doc_date": "07/08/2022"}
{"filename": "Transmittal Sheet 01_08_2024.pdf", "client_name": "Zenith Realty Development Corp.", "doc_date": "01/08/2024"}
{"filename": "Certificate of Incorporation 2025030195697-02.pdf", "client_name": "Vertex Consultancy, OPC", "doc_date": "03/28/2025"}
{"filename": "Certificate of Registration 041RC20250000005534.pdf", "client_name": "Atlas Pharmaceuticals, Inc.", "doc_date": "10/20/2025"}
{"filename": "Authority to Print 041RC20250000005534.pdf", "client_name": "Atlas Pharmaceuticals, Inc.", "doc_date": "10/20/2025"}
{"filename": "Application for Registration 682-974-124-00000.pdf", "client_name": "Atlas Pharmaceuticals, Inc.", "doc_date": "10/20/2025"}
{"filename": "Monthly Documentary Stamp Tax Declaration Return 08_2025.pdf", "client_name": "Atlas Pharmaceuticals, Inc.", "doc_date": "08/2025"}
{"filename": "Certificate of Incorporation 2025060206219-60.pdf", "client_name": "Summit Trade Distribution, Inc.", "doc_date": null}
{"filename": "Unrecognized.pdf", "client_name": null, "doc_date": null}

"""

def pdf_page_to_base64_image(file_path: str, page_num: int = 0, dpi: int = 300) -> Optional[str]:
    try:
        import fitz
        import base64
        with fitz.open(file_path) as doc:
            if len(doc) == 0:
                return None
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            return f"data:image/png;base64,{b64_str}"
    except Exception as e:
        logger.error(f"Error rendering PDF page to image for Vision OCR: {e}")
        return None

def pdf_to_base64_images(file_path: str, max_pages: int = 3, dpi: int = 250) -> List[str]:
    """
    Renders key pages of a PDF (e.g. Page 1 and the last/signature page) to base64 images for Vision AI OCR.
    Automatically identifies notarial acknowledgment sections (Doc. No., Notary Public) and appends
    an enlarged, high-resolution close-up crop for precise handwriting recognition.
    """
    images = []
    try:
        import fitz
        import base64
        with fitz.open(file_path) as doc:
            total_pages = len(doc)
            if total_pages == 0:
                return []
            
            # Select pages to render: always page 1 (index 0); if multi-page, include the last page
            if total_pages == 1:
                pages_to_render = [0]
            elif total_pages == 2:
                pages_to_render = [0, 1]
            else:
                pages_to_render = [0]
                if max_pages >= 3 and total_pages > 2:
                    pages_to_render.append(1)
                pages_to_render.append(total_pages - 1)

            for p_num in pages_to_render:
                page = doc[p_num]
                pix = page.get_pixmap(dpi=dpi)
                img_bytes = pix.tobytes("png")
                b64_str = base64.b64encode(img_bytes).decode("utf-8")
                images.append(f"data:image/png;base64,{b64_str}")

            # Check for Notarial acknowledgment / Doc. No. markers across pages to extract high-res crop
            for p in doc:
                rects = (
                    p.search_for('Doc. No') or 
                    p.search_for('Doc No') or 
                    p.search_for('Doc.') or 
                    p.search_for('Notary Public') or 
                    p.search_for('Series of')
                )
                if rects:
                    r = rects[0]
                    clip_rect = fitz.Rect(
                        max(0, r.x0 - 20),
                        max(0, r.y0 - 20),
                        min(p.rect.width, r.x0 + 175),
                        min(p.rect.height, r.y0 + 140)
                    )
                    crop_pix = p.get_pixmap(clip=clip_rect, dpi=350)
                    crop_bytes = crop_pix.tobytes("png")
                    crop_b64 = base64.b64encode(crop_bytes).decode("utf-8")
                    images.append(f"data:image/png;base64,{crop_b64}")
                    logger.debug(f"Appended high-resolution notarial block close-up crop for {file_path}")
                    break
    except Exception as e:
        logger.error(f"Error rendering PDF pages to images for Vision OCR: {e}")
    return images

def parse_ai_suggested_metadata(ai_response: str) -> Dict[str, Optional[str]]:
    result = {
        "filename": None,
        "client_name": None,
        "doc_date": None
    }
    if not ai_response:
        return result
    try:
        clean_text = ai_response.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r'^```(?:json)?\s*', '', clean_text, flags=re.IGNORECASE)
            clean_text = re.sub(r'\s*```$', '', clean_text)

        data = json.loads(clean_text)
        if isinstance(data, dict):
            if "filename" in data and data["filename"]:
                result["filename"] = sanitize_filename(str(data["filename"]))
            if "client_name" in data and data["client_name"]:
                result["client_name"] = format_client_name(str(data["client_name"]).strip())
            if "doc_date" in data and data["doc_date"]:
                result["doc_date"] = str(data["doc_date"]).strip()
            return result
    except Exception:
        pass

    fname = parse_ai_suggested_filename(ai_response)
    result["filename"] = fname
    return result

def parse_ai_suggested_filename(ai_response: str) -> Optional[str]:
    if not ai_response:
        return None
    try:
        clean_text = ai_response.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r'^```(?:json)?\s*', '', clean_text, flags=re.IGNORECASE)
            clean_text = re.sub(r'\s*```$', '', clean_text)

        # 1. Try parsing full JSON object
        data = json.loads(clean_text)
        if isinstance(data, dict) and "filename" in data:
            return sanitize_filename(str(data["filename"]))
    except Exception:
        pass

    # 2. Extract specifically value of "filename": "..."
    json_field = re.search(r'"filename"\s*:\s*"([^"]+)"', ai_response, re.IGNORECASE)
    if json_field:
        return sanitize_filename(json_field.group(1).strip())

    return None

def sanitize_filename(filename: str) -> str:
    # Strip any extra doc_type or json artifacts accidentally merged in
    filename = re.sub(r',\s*doc_type.*$', '', filename, flags=re.IGNORECASE).strip()
    filename = re.sub(r'["{}]', '', filename).strip()
    
    # Strip leading Re: / Re_ / Re
    filename = re.sub(r'^Re[_\s:]+', '', filename, flags=re.IGNORECASE).strip()

    # Replace slashes with space so "Declaration/Return" becomes "Declaration Return"
    filename = re.sub(r'[/\\]+', ' ', filename)

    # Clean invalid filename characters
    cleaned = re.sub(r'[*?"<>|:]', '', filename).strip()

    # Fix accidental concatenation of DeclarationReturn -> Declaration Return
    cleaned = re.sub(r'\bDeclarationReturn\b', 'Declaration Return', cleaned, flags=re.IGNORECASE)

    # Normalize multiple whitespace
    cleaned = re.sub(r'[ \t]+', ' ', cleaned).strip()

    # Normalize Doc. No. formatting (e.g. Doc. No: 387 / Doc No 387 -> Doc. No. 387)
    cleaned = re.sub(r'\bDoc\.?\s*No\.?\s*[:\-#]?\s*(\d+)', r'Doc. No. \1', cleaned, flags=re.IGNORECASE)

    # Fix trailing underscore between Title and numerical date (e.g. Title_09_22_2017.pdf -> Title 09_22_2017.pdf)
    cleaned = re.sub(r'(?<!\d)_\s*(\d{2}_\d{2}_\d{4}\.pdf)$', r' \1', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(?<!\d)_\s*(\d{2}_\d{4}\.pdf)$', r' \1', cleaned, flags=re.IGNORECASE)

    # Check for Liquidation of Deposit FIRST before SOA/OPE check
    if re.search(r'\b(?:Liquidation|Accounting)\s+of\s+Deposit\b', cleaned, re.IGNORECASE):
        # Format: Liquidation of Deposit for Out-of-Pocket Expenses MM_DD_YYYY.pdf
        date_match = re.search(r'(\d{2})_(\d{2})_(\d{4})', cleaned)
        if date_match:
            date_str = f"{date_match.group(1)}_{date_match.group(2)}_{date_match.group(3)}"
        else:
            digits_8 = re.search(r'(\d{2})(\d{2})(\d{4})', cleaned)
            if digits_8:
                date_str = f"{digits_8.group(1)}_{digits_8.group(2)}_{digits_8.group(3)}"
            else:
                date_str = ''

        if date_str:
            cleaned = f"Liquidation of Deposit for Out-of-Pocket Expenses {date_str}.pdf"
        elif not cleaned.lower().startswith("liquidation of deposit"):
            cleaned = f"Liquidation of Deposit for Out-of-Pocket Expenses.pdf"
    else:
        # If filename contains Statement of Account, SOA, Out-of-Pocket Expenses, or OPE:
        # ALWAYS enforce numbers-only naming and strip text like "Statement of Account" or "SOA" prefix
        is_soa_or_ope = re.search(r'(?:Statement\s*of\s*Account|SOA|Out-of-Pocket\s*Expenses|OPE)', cleaned, re.IGNORECASE)
        if is_soa_or_ope:
            # Check for OPE reference number first (e.g. OPE-1185 -> 1185.pdf)
            ope_match = re.search(r'OPE[-_\s:]*(\d+)', cleaned, re.IGNORECASE)
            if ope_match:
                cleaned = f"{ope_match.group(1)}.pdf"
            else:
                # Extract all digits in the filename and strip words like Statement of Account / SOA prefix
                digits_only = re.sub(r'\D', '', cleaned)
                if digits_only:
                    cleaned = f"{digits_only}.pdf"

    # If filename contains Summary of Services or Services Rendered:
    # Ensure it is strictly "Summary of Services <Period>.pdf" without extra prefix words like "Litigation -", "Rendered", etc.
    if re.search(r'\b(?:Summary\s+of\s+Services|Services\s+Rendered)\b', cleaned, re.IGNORECASE):
        months = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
        period_match = re.search(r'\b((?:' + months + r'\s+(?:\d{4}\s+)?(?:to|-)\s+)?' + months + r'\s+\d{4})\b', cleaned, re.IGNORECASE)
        if period_match:
            cleaned = f"Summary of Services {period_match.group(1)}.pdf"

    if not cleaned.lower().endswith('.pdf'):
        cleaned += '.pdf'
    return cleaned

def worker_loop(
    work_queue: queue.Queue,
    api_dispatcher: AIAPIDispatcher,
    stop_event: threading.Event,
    config: PipelineConfig,
    output_dir: Optional[str] = None,
    processed_records: Optional[List[Dict[str, Any]]] = None,
    client_mgr: Optional[Any] = None,
    event_callback: Optional[Any] = None
) -> None:
    """
    Asynchronous worker thread that dequeues file targets from the reactive watchdog queue,
    verifies write stabilization, dispatches AI API prompts, classifies/renames PDFs, 
    and directly routes them to the appropriate client folder with sticky client context.
    """
    thread_name = threading.current_thread().name
    logger.info(f"Worker thread '{thread_name}' active and waiting for file events.")

    while not stop_event.is_set():
        try:
            file_path = work_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            logger.info(f"[{thread_name}] Processing queued item: {file_path}")

            if not os.path.exists(file_path):
                logger.warning(f"[{thread_name}] File does not exist: {file_path}. Skipping.")
                continue

            if event_callback:
                try:
                    event_callback({
                        "type": "stabilizing",
                        "file_path": file_path,
                        "filename": os.path.basename(file_path),
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception:
                    pass

            # Step 1: Stability verification (wait for file write to complete)
            wait_for_file_stability(
                file_path=file_path,
                timeout=config.stability_timeout,
                poll_interval=config.stability_poll_interval
            )

            if not os.path.exists(file_path):
                logger.warning(f"[{thread_name}] File no longer exists after stability check: {file_path}. Skipping.")
                continue

            if event_callback:
                try:
                    event_callback({
                        "type": "analyzing",
                        "file_path": file_path,
                        "filename": os.path.basename(file_path),
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception:
                    pass

            # Step 2: Read payload & Invoke AI API Dispatcher using Vision AI OCR
            ai_target_name = None
            extracted_client_name = None
            extracted_doc_date = None

            try:
                response = None
                if file_path.lower().endswith('.pdf'):
                    b64_imgs = pdf_to_base64_images(file_path)
                    if b64_imgs:
                        logger.info(f"[{thread_name}] Dispatching {len(b64_imgs)} visual document page(s) to AI Vision OCR model ({config.model_name})...")
                        
                        # Read page 1 text excerpt to ground the vision AI model in ground-truth text
                        p1_excerpt = ""
                        try:
                            import fitz
                            with fitz.open(file_path) as d:
                                if len(d) > 0:
                                    p1_excerpt = d[0].get_text()[:1500].strip()
                        except Exception:
                            pass

                        prompt_text = "Perform visual AI OCR on this document image (including first and last/signature pages and zoomed notary crop). Read all dates, numbers, headers, Doc. No., and client names visually and return the metadata JSON."
                        if p1_excerpt:
                            prompt_text = f"Document text excerpt from Page 1:\n---\n{p1_excerpt}\n---\n\n{prompt_text}"

                        response = api_dispatcher.dispatch_vision(
                            image_b64_url=b64_imgs,
                            system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
                            text_prompt=prompt_text
                        )

                if not response:
                    # Text fallback for non-PDF or image rendering fallback
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    if content.strip():
                        response = api_dispatcher.dispatch_prompt(
                            prompt_text=content[:config.max_payload_length],
                            system_prompt=CLASSIFICATION_SYSTEM_PROMPT
                        )

                if response:
                    metadata = parse_ai_suggested_metadata(response)
                    ai_target_name = metadata.get("filename")
                    extracted_client_name = metadata.get("client_name")
                    extracted_doc_date = metadata.get("doc_date")

                    if ai_target_name:
                        logger.info(f"[{thread_name}] AI Vision OCR classified target filename: '{ai_target_name}'")

                    if output_dir:
                        os.makedirs(output_dir, exist_ok=True)
                        out_filename = f"{os.path.basename(file_path)}.response.txt"
                        out_path = os.path.join(output_dir, out_filename)
                        with open(out_path, 'w', encoding='utf-8') as out_f:
                            out_f.write(response)
                        logger.info(f"[{thread_name}] Saved AI response to: {out_path}")
            except Exception as e:
                logger.error(f"[{thread_name}] Error processing document with AI Vision OCR: {e}", exc_info=True)

            # Step 3: Direct routing to Client directory with sticky client context
            file_name = os.path.basename(file_path)

            if ai_target_name:
                target_name = ai_target_name
            elif file_name.lower().endswith('.pdf'):
                target_name = classify_pdf_by_rules(file_path)
            else:
                target_name = file_name

            # Authoritative client extraction & validation from PDF ground-truth text layer
            if file_path.lower().endswith('.pdf'):
                from src.client_manager import extract_client_name_from_pdf, INVALID_CLIENT_PHRASES
                rule_client = extract_client_name_from_pdf(file_path)
                if rule_client and rule_client.lower() != "general clients" and not any(k in rule_client.lower() for k in INVALID_CLIENT_PHRASES):
                    is_bank = any(b in (extracted_client_name or '').lower() for b in ['bank', 'unibank', 'bdo unibank', 'bdo leasing'])
                    
                    # Verify if AI suggested client actually exists in document text
                    pdf_txt = ""
                    try:
                        import fitz
                        with fitz.open(file_path) as d:
                            pdf_txt = '\n'.join([p.get_text() for p in d[:3]]).lower()
                    except Exception:
                        pass

                    ai_client_str = (extracted_client_name or '').lower()
                    ai_words = [w for w in re.sub(r'[^a-z0-9\s]', ' ', ai_client_str).split() if len(w) > 3]
                    ai_not_in_doc = bool(extracted_client_name and ai_words and not any(w in pdf_txt for w in ai_words))
                    ai_is_invalid_phrase = any(k in ai_client_str for k in INVALID_CLIENT_PHRASES)

                    if not extracted_client_name or is_bank or ai_not_in_doc or ai_is_invalid_phrase or (rule_client.lower() in pdf_txt and ai_client_str != rule_client.lower()):
                        logger.info(f"[{thread_name}] Setting client to verified issuing entity from PDF text: '{rule_client}' (AI suggested: '{extracted_client_name}')")
                        extracted_client_name = rule_client

            if client_mgr is not None:
                client_name, is_inherited = client_mgr.resolve_client_name(extracted_client_name)
                if is_inherited:
                    logger.info(f"[{thread_name}] Document has no explicit client. Inheriting active client context: '{client_name}'")
                else:
                    logger.info(f"[{thread_name}] Direct Routing: Active client identified as '{client_name}'")

                dest_path = client_mgr.route_file_to_client(
                    src_file=file_path,
                    client_name=client_name,
                    doc_date=extracted_doc_date,
                    target_filename=target_name
                )
                logger.info(f"[{thread_name}] SUCCESS: Directly routed '{file_name}' -> '{client_name}/{os.path.basename(dest_path)}'")

                if processed_records is not None:
                    processed_records.append({
                        "file_path": dest_path,
                        "filename": os.path.basename(dest_path),
                        "client_name": client_name,
                        "doc_date": extracted_doc_date
                    })

                if event_callback:
                    try:
                        event_callback({
                            "type": "completed",
                            "src_path": file_path,
                            "src_filename": file_name,
                            "dest_path": dest_path,
                            "dest_filename": os.path.basename(dest_path),
                            "client_name": client_name or "General Clients",
                            "doc_date": extracted_doc_date or "",
                            "timestamp": time.strftime("%H:%M:%S")
                        })
                    except Exception:
                        pass
            else:
                current_dir = os.path.dirname(os.path.abspath(file_path))
                parent_dir_name = os.path.basename(current_dir).lower()
                if parent_dir_name in ('temporary', 'unproccesed', 'unprocessed', 'temp'):
                    target_folder = os.path.dirname(current_dir)
                else:
                    target_folder = current_dir

                target_name, dest_path = resolve_filename_collision(target_folder, target_name, file_path)

                # Retry move operation to withstand transient Windows file locks
                moved = False
                for attempt in range(4):
                    try:
                        shutil.move(file_path, dest_path)
                        moved = True
                        break
                    except PermissionError:
                        time.sleep(0.3)

                if not moved:
                    shutil.move(file_path, dest_path)

                logger.info(f"[{thread_name}] SUCCESS: Relocated '{file_name}' -> '{os.path.basename(target_folder)}/{target_name}'")

                if processed_records is not None:
                    processed_records.append({
                        "file_path": dest_path,
                        "filename": target_name,
                        "client_name": extracted_client_name,
                        "doc_date": extracted_doc_date
                    })

                if event_callback:
                    try:
                        event_callback({
                            "type": "completed",
                            "src_path": file_path,
                            "src_filename": file_name,
                            "dest_path": dest_path,
                            "dest_filename": target_name,
                            "client_name": extracted_client_name or "General Clients",
                            "doc_date": extracted_doc_date or "",
                            "timestamp": time.strftime("%H:%M:%S")
                        })
                    except Exception:
                        pass

        except FileStabilityError as fse:
            logger.error(f"[{thread_name}] Stability error for {file_path}: {fse}")
            if event_callback:
                try:
                    event_callback({
                        "type": "error",
                        "file_path": file_path,
                        "filename": os.path.basename(file_path),
                        "error": str(fse),
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception:
                    pass
        except Exception as ex:
            logger.error(f"[{thread_name}] Error processing {file_path}: {ex}", exc_info=True)
            if event_callback:
                try:
                    event_callback({
                        "type": "error",
                        "file_path": file_path,
                        "filename": os.path.basename(file_path),
                        "error": str(ex),
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception:
                    pass
        finally:
            work_queue.task_done()

    logger.info(f"Worker thread '{thread_name}' terminated.")
