import os
import shutil
import hashlib
import fitz
import re
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

def extract_date_from_text(text: str) -> Optional[str]:
    """
    Extracts date in MM_DD_YYYY format from text if found, else returns None.
    """
    months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    
    # Keyword-associated date search (e.g. "Date: January 8, 2024" or "January 8, 2024")
    kw_pattern = r'(?:date|transmittal|dated)?\s*:?\s*(' + '|'.join(months) + r')\s+(\d{1,2}),?\s+(\d{4})'
    kw_match = re.search(kw_pattern, text, re.IGNORECASE)
    if kw_match:
        m_str, d_str, y_str = kw_match.groups()
        try:
            dt = datetime.strptime(f"{m_str} {int(d_str):02d} {y_str}", '%B %d %Y')
            return dt.strftime('%m_%d_%Y')
        except ValueError:
            pass

    # Generic month pattern
    month_pattern = r'(' + '|'.join(months) + r')\s+(\d{1,2}),?\s+(\d{4})'
    for match in re.finditer(month_pattern, text, re.IGNORECASE):
        m_str, d_str, y_str = match.groups()
        try:
            dt = datetime.strptime(f"{m_str} {int(d_str):02d} {y_str}", '%B %d %Y')
            return dt.strftime('%m_%d_%Y')
        except ValueError:
            continue

    # Numeric date pattern (MM/DD/YYYY or YYYY-MM-DD)
    num_match = re.search(r'\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b', text)
    if num_match:
        m_str, d_str, y_str = num_match.groups()
        try:
            dt = datetime.strptime(f"{int(m_str):02d} {int(d_str):02d} {y_str}", '%m %d %Y')
            return dt.strftime('%m_%d_%Y')
        except ValueError:
            pass

    return None

def parse_date_from_text(text: str) -> str:
    """
    Extracts date in MM_DD_YYYY format from text.
    Prefers dates associated with keywords or full month patterns.
    """
    dt = extract_date_from_text(text)
    return dt if dt is not None else "01_01_2023"

def resolve_filename_collision(folder: str, filename: str, src_file_path: Optional[str] = None) -> Tuple[str, str]:
    """
    Resolves filename collisions in target folder by appending numerical suffixes _2, _3, _4, etc.
    Returns (final_filename, final_dest_path).
    """
    dest_path = os.path.join(folder, filename)
    if not os.path.exists(dest_path) or dest_path == src_file_path:
        return filename, dest_path

    base, ext = os.path.splitext(filename)
    
    # 1. If base has MM_DD_YYYY date followed by a suffix (e.g. Title 12_09_2020_2 or Title 12_09_2020_1786074594)
    m = re.match(r'^(.*\s\d{2}_\d{2}_\d{4})_\d+$', base)
    if m:
        clean_base = m.group(1)
    else:
        # 2. If base ends with MM_DD_YYYY or 8-digit date or 4-6 digit SOA number or Doc. No. <num>, preserve it
        if re.search(r'\s\d{2}_\d{2}_\d{4}$', base) or re.search(r'^\d{8}$', base) or re.search(r'^\d{4,6}$', base) or re.search(r'Doc\.\s*No\.\s*\d+$', base, re.IGNORECASE):
            clean_base = base
        else:
            clean_base = re.sub(r'_\d+$', '', base)

    counter = 2
    while True:
        candidate_name = f"{clean_base}_{counter}{ext}"
        candidate_path = os.path.join(folder, candidate_name)
        if not os.path.exists(candidate_path) or candidate_path == src_file_path:
            return candidate_name, candidate_path
        counter += 1

def organize_directory(temp_dir: str, parent_dir: Optional[str] = None) -> List[Tuple[str, str]]:
    """
    Generic directory organizer. Classifies and renames files in temp_dir 
    and moves them to parent_dir (or the directory above temp_dir).
    """
    if not os.path.exists(temp_dir):
        logger.error(f"Target directory does not exist: {temp_dir}")
        return []

    if parent_dir is None:
        parent_dir = os.path.dirname(os.path.abspath(temp_dir))

    moved_records: List[Tuple[str, str]] = []
    for filename in sorted(os.listdir(temp_dir)):
        temp_file_path = os.path.join(temp_dir, filename)
        if os.path.isfile(temp_file_path):
            if filename.lower().endswith('.pdf'):
                target_filename = classify_pdf_by_rules(temp_file_path)
            else:
                target_filename = filename

            target_filename, dest_path = resolve_filename_collision(parent_dir, target_filename, temp_file_path)

            shutil.move(temp_file_path, dest_path)
            moved_records.append((filename, dest_path))
            logger.info(f"Moved '{filename}' -> '{target_filename}'")

    return moved_records


def classify_pdf_by_rules(file_path: str) -> str:
    """
    Extracts text from PDF and determines standardized filename based on learned rules.
    """
    with fitz.open(file_path) as doc:
        text_p1 = doc[0].get_text() if len(doc) > 0 else ""
        text_full = '\n'.join([page.get_text() for page in doc])

    # Rule 1: Liquidation of Deposit for Out-of-Pocket Expenses
    if 'liquidation of deposit' in text_full.lower() or 'accounting of deposit' in text_full.lower():
        dt_str = parse_date_from_text(text_full)
        return f"Liquidation of Deposit for Out-of-Pocket Expenses {dt_str}.pdf"

    # Rule 2: Statement of Account / SOA / OPE -> numerical digits only (e.g., OPE-1185 -> 1185.pdf, 2022-0129 -> 20220129.pdf)
    # Check if header/title (especially on Page 1 or full text) indicates Statement of Account / SOA / OPE
    is_soa_or_ope = any(k in text_p1.lower() for k in ['statement of account', 'soa', 'out-of-pocket', 'ope']) or \
                    any(k in text_full.lower() for k in ['statement of account', 'soa', 'out-of-pocket', 'ope'])

    if is_soa_or_ope:
        ope_match = re.search(r'\bOPE[-_\s:]*(\d+)', text_full, re.IGNORECASE)
        if ope_match:
            return f"{ope_match.group(1)}.pdf"

        no_match = re.search(r'\bNo\.?\s*[:_-]?\s*([0-9]+(?:[-_][0-9]+)*)\b', text_p1 if text_p1 else text_full, re.IGNORECASE)
        if no_match:
            digits_only = re.sub(r'\D', '', no_match.group(1))
            if digits_only:
                return f"{digits_only}.pdf"

        soa_direct = re.search(r'(?:SOA|STATEMENT\s*OF\s*ACCOUNT)\s*:?\s*(?:No\.?)?\s*[-_]?\s*(?:OPE[-_\s:]*)?([0-9]+(?:[-_][0-9]+)*)', text_full, re.IGNORECASE)
        if soa_direct:
            digits_only = re.sub(r'\D', '', soa_direct.group(1))
            if digits_only:
                return f"{digits_only}.pdf"

    # Rule 3: Transmittal Sheet (Must have explicit header)
    if 'transmittal sheet' in text_p1.lower() or 'transmittal sheet' in text_full.lower():
        dt_str = parse_date_from_text(text_p1 if 'transmittal sheet' in text_p1.lower() else text_full)
        return f"Transmittal Sheet {dt_str}.pdf"

    # Rule 4: Summary of Services / Services Rendered
    if 'services rendered' in text_full.lower() or 'summary of services' in text_full.lower():
        months = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
        # Matches "February to June 2019", "October 2022 to March 2023", "October 2022 - March 2023", etc.
        range_pattern = r'\b((?:' + months + r'\s+(?:\d{4}\s+)?(?:to|-)\s+)?' + months + r'\s+\d{4})\b'
        range_match = re.search(range_pattern, text_full, re.IGNORECASE)
        if range_match:
            return f"Summary of Services {range_match.group(1)}.pdf"
        dt_str = parse_date_from_text(text_full)
        return f"Summary of Services {dt_str}.pdf"

    # Rule 5: Certificates & Registration Documents (Certificate of Incorporation, Certificate of Registration, Authority to Print, Application for Registration, Secretary's Certificate, etc.)
    # CRITICAL: ONLY check Page 1 (text_p1). NEVER fall back to dates from inner pages (receipts, notary, letters, etc.).
    cert_checks = [
        ("Certificate of Incorporation", ["certificate of incorporation", "cert. of incorporation"]),
        ("Certificate of Registration", ["certificate of registration", "bir form 2303", "form 2303", "form no. 2303"]),
        ("Authority to Print", ["authority to print", "bir form 1906", "form 1906", "form no. 1906"]),
        ("Application for Registration", ["application for registration", "bir form 1903", "form 1903", "bir form 1901", "form 1901", "bir form 1902", "form 1902", "bir form 1904", "form 1904", "bir form 1905", "form 1905"]),
        ("Secretary's Certificate", ["secretary's certificate", "secretarys certificate", "secretary certificate"]),
        ("Certificate of Filing", ["certificate of filing"]),
        ("Certificate", ["certificate"])
    ]
    for cert_title, keywords in cert_checks:
        if any(kw in text_p1.lower() for kw in keywords) or any(kw in text_full.lower() for kw in keywords):
            # 1. Certificate of Registration (e.g. BIR Form 2303) -> Extract OCN number on Page 1
            if cert_title == "Certificate of Registration":
                ocn_match = re.search(r'OCN\s*[:\-#]?\s*([0-9A-Za-z]+)', text_p1, re.IGNORECASE)
                if ocn_match:
                    ocn_val = ocn_match.group(1).strip()
                    return f"Certificate of Registration {ocn_val}.pdf"
                
                tin_match = re.search(r'\b(\d{3}[-\s]\d{3}[-\s]\d{3}[-\s]\d{3,5})\b', text_p1)
                if tin_match:
                    clean_tin = re.sub(r'\s+', '-', tin_match.group(1).strip())
                    return f"Certificate of Registration {clean_tin}.pdf"
                
                p1_date = extract_date_from_text(text_p1)
                if p1_date:
                    return f"Certificate of Registration {p1_date}.pdf"
                return "Certificate of Registration.pdf"

            # 2. Authority to Print (e.g. BIR Form 1906) -> Extract OCN number on Page 1
            if cert_title == "Authority to Print":
                ocn_match = re.search(r'OCN\s*[:\-#]?\s*([0-9A-Za-z]+)', text_p1, re.IGNORECASE)
                if ocn_match:
                    ocn_val = ocn_match.group(1).strip()
                    return f"Authority to Print {ocn_val}.pdf"
                
                atp_match = re.search(r'(?:ATP\s*No\.?|Authority\s*to\s*Print\s*No\.?)\s*[:\-#]?\s*([0-9A-Za-z\-]+)', text_p1, re.IGNORECASE)
                if atp_match:
                    return f"Authority to Print {atp_match.group(1).strip()}.pdf"
                
                p1_date = extract_date_from_text(text_p1)
                if p1_date:
                    return f"Authority to Print {p1_date}.pdf"
                return "Authority to Print.pdf"

            # 3. Application for Registration (e.g. BIR Form 1903/1901) -> Extract TIN on Page 1
            if cert_title == "Application for Registration":
                tin_match = re.search(r'\b(\d{3}[-\s]\d{3}[-\s]\d{3}[-\s]\d{3,5})\b', text_p1)
                if tin_match:
                    clean_tin = re.sub(r'\s+', '-', tin_match.group(1).strip())
                    return f"Application for Registration {clean_tin}.pdf"
                
                # Look for 9-13 standalone digits in TIN boxes
                tin_digits = re.search(r'(?:TIN|Taxpayer\s*Identification)\s*[:\-#]?\s*(\d{9,14})', text_p1, re.IGNORECASE)
                if tin_digits:
                    d = tin_digits.group(1).strip()
                    return f"Application for Registration {d[:3]}-{d[3:6]}-{d[6:9]}-{d[9:]}.pdf"
                
                return "Application for Registration.pdf"

            # 4. Certificate of Incorporation -> Check Company Reg. No. on Page 1 first
            if cert_title == "Certificate of Incorporation":
                id_match = re.search(r'(?:COMPANY\s*REG\.?\s*(?:NO\.?|PtiO\.?|N[O0]\.?)?|SEC\s*(?:Reg\.?|Registration)?\s*(?:NO\.?|N[O0]\.?)?|Registration\s*NO\.?|CN\s*NO\.?)\s*[:\-#]?\s*([0-9A-Za-z]+(?:-[0-9A-Za-z]+)+)', text_p1, re.IGNORECASE)
                if id_match:
                    reg_no = id_match.group(1).strip()
                    return f"Certificate of Incorporation {reg_no}.pdf"
                
                # Standalone pattern for registration number e.g. 2025030195697-02
                reg_standalone = re.search(r'\b(\d{10,}(?:-[0-9A-Za-z]+)?)\b', text_p1)
                if reg_standalone:
                    return f"Certificate of Incorporation {reg_standalone.group(1).strip()}.pdf"
                
                p1_date = extract_date_from_text(text_p1)
                if p1_date:
                    return f"Certificate of Incorporation {p1_date}.pdf"
                
                return "Certificate of Incorporation.pdf"

            # 5. Secretary's Certificate and other Certificates:
            if cert_title == "Secretary's Certificate":
                doc_no_match = re.search(r'Doc\.?\s*No\.?\s*[:\-#]?\s*(\d+)', text_full, re.IGNORECASE)
                if doc_no_match:
                    doc_no_val = doc_no_match.group(1).strip()
                    return f"Secretary's Certificate Doc. No. {doc_no_val}.pdf"

            p1_date = extract_date_from_text(text_p1)
            if p1_date:
                return f"{cert_title} {p1_date}.pdf"
            
            # If no date on first page, search for ID Number / Reference Number on first page
            id_match = re.search(r'(?:SEC\s*(?:Reg\.?|Registration)?\s*(?:No\.?)?|Company\s*Reg\.?\s*(?:No\.?)?|Registration\s*No\.?|Certificate\s*No\.?|CN\s*No\.?|ID\s*No\.?|No\.?)\s*[:\-#]?\s*([0-9A-Za-z]+(?:-[0-9A-Za-z]+)+)', text_p1, re.IGNORECASE)
            if id_match:
                return f"{cert_title} {id_match.group(1).strip()}.pdf"
            
            id_standalone = re.search(r'\b(\d{8,}(?:-[0-9A-Za-z]+)?)\b', text_p1)
            if id_standalone:
                return f"{cert_title} {id_standalone.group(1).strip()}.pdf"
                
            return f"{cert_title}.pdf"

    # Rule 6: Tax Returns & Declarations (e.g. Monthly Documentary Stamp Tax Declaration Return)
    if 'documentary stamp tax' in text_p1.lower() or 'documentary stamp tax' in text_full.lower() or 'bir form 2000' in text_p1.lower() or 'form 2000' in text_p1.lower():
        dt_month = re.search(r'\b(0[1-9]|1[0-2])[/.\-](\d{4})\b', text_p1)
        if dt_month:
            return f"Monthly Documentary Stamp Tax Declaration Return {dt_month.group(1)}_{dt_month.group(2)}.pdf"
        p1_date = extract_date_from_text(text_p1)
        if p1_date:
            return f"Monthly Documentary Stamp Tax Declaration Return {p1_date}.pdf"
        return "Monthly Documentary Stamp Tax Declaration Return.pdf"

    return "Unrecognized.pdf"
