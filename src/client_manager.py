import os
import re
import shutil
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from src.organizer import resolve_filename_collision

import time
import threading

logger = logging.getLogger(__name__)

MONTH_MAP = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sept", 10: "Oct", 11: "Nov", 12: "Dec"
}

SPECIAL_CLIENT_CASES = {
    "INC": "Inc.",
    "INC.": "Inc.",
    "CORP": "Corp",
    "CORP.": "Corp",
    "LLC": "LLC",
    "OPC": "OPC",
    "LTD": "Ltd.",
    "LTD.": "Ltd.",
    "CO": "Co.",
    "CO.": "Co.",
    "MR": "Mr.",
    "MR.": "Mr.",
    "MRS": "Mrs.",
    "MRS.": "Mrs.",
    "MS": "Ms.",
    "MS.": "Ms.",
    "DR": "Dr.",
    "DR.": "Dr.",
    "II": "II",
    "III": "III",
    "IV": "IV",
    "JR": "Jr.",
    "JR.": "Jr.",
    "SR": "Sr.",
    "SR.": "Sr.",
}

KNOWN_ACRONYMS = {
    "ABC", "XYZ", "OPC", "LLC", "GRM", "BIR", "SEC",
    "TIN", "OCN", "BDO", "BPI", "SM", "RCBC", "IBM", "SMC",
    "DTI", "SSS", "DOLE", "PLDT", "USA", "PH", "AIM", "ABS", "CBN", "GMA"
}


COMMON_SHORT_WORDS = {
    "THE", "AND", "FOR", "NEW", "ONE", "TWO", "BIG", "TOP", "RED", "SUN",
    "SEA", "SAN", "STA", "STO", "DE", "DEL", "LA", "LAS", "LOS", "VAN", "VON",
    "OF", "IN", "ON", "AT", "BY", "TO", "ALL", "AIR", "BAY", "DAY", "ECO", "GAS",
    "HUB", "KEY", "LAW", "MAX", "NET", "OIL", "PRO", "SKY", "TAX", "WAY"
}

def _format_word_token(token: str) -> str:
    # Separate any trailing punctuation (like comma, semicolon)
    m = re.match(r'^([A-Za-z0-9\.\-\']+?)([,;:]*)$', token)
    if m:
        core = m.group(1)
        suffix = m.group(2)
    else:
        core = token
        suffix = ""

    upper_core = core.upper()

    # 1. Check known cases (e.g. INC, CORP, LLC, OPC, MR)
    if upper_core in SPECIAL_CLIENT_CASES:
        return SPECIAL_CLIENT_CASES[upper_core] + suffix

    # 2. Known corporate/business acronyms (e.g. ABC, XYZ, LLC, OPC)
    if upper_core in KNOWN_ACRONYMS:
        return upper_core + suffix

    # 3. Alphanumeric tokens / initials with digits (e.g. J3, 3M, G4S)
    if re.search(r'[A-Za-z]', core) and re.search(r'\d', core):
        return upper_core + suffix

    # 4. Single letter initials (e.g. "C." or "C" or "A.")
    if len(core.rstrip('.')) == 1:
        return upper_core + suffix

    # 5. Acronym / initials check: 2 to 5 characters with NO vowels (A, E, I, O, U, Y)
    # E.g. GRM, RCBC, KLM, QRS
    letters_only = re.sub(r'[^A-Za-z]', '', core).upper()

    if 2 <= len(letters_only) <= 5 and not any(v in letters_only for v in 'AEIOUY'):
        return upper_core + suffix

    # 5b. Short uppercase acronyms/initials (2 to 3 characters) that are not common English words (e.g. BDO, BPI, URC)
    if 2 <= len(letters_only) <= 3 and upper_core not in COMMON_SHORT_WORDS:
        return upper_core + suffix

    # 6. Hyphenated words
    if '-' in core:
        parts = core.split('-')
        formatted_parts = [_format_word_token(p) for p in parts]
        return '-'.join(formatted_parts) + suffix

    # 7. Standard word: Title Case (e.g. GROUP -> Group, CORPORATION -> Corporation)
    if core.isupper() or core.islower():
        formatted_core = core.capitalize()
    else:
        formatted_core = core

    return formatted_core + suffix

def format_client_name(name: Optional[str]) -> str:
    """
    Formats client name into Proper/Title Case while preserving true business initials/acronyms
    (e.g. 'Global Group Corporation', 'Bluestar J3 Corp.', 'Nexus World Media, Inc.',
    'Cascade Ventures, Corp.').
    """
    if not name or not str(name).strip():
        return "General Clients"


    clean_name = str(name).strip().strip('"\'')
    if not clean_name:
        return "General Clients"

    # Strip trailing commas or periods from full string before tokenization
    clean_name = re.sub(r'[\r\n\t]+', ' ', clean_name).strip()

    words = clean_name.split()
    formatted_words = [_format_word_token(word) for word in words if word.strip()]

    result = ' '.join(formatted_words)
    # Ensure space after comma
    result = re.sub(r',([A-Za-z])', r', \1', result)
    # Clean redundant punctuation like ".,", or trailing comma
    result = re.sub(r'\.,', '.', result)
    result = result.rstrip(',').strip()

    return result if result else "General Clients"

def parse_date_to_dt(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None

    date_str = date_str.strip()

    formats = [
        "%m/%d/%Y", "%m-%d-%Y", "%m_%d_%Y",
        "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
        "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d %B %Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Regex search for MM_DD_YYYY or MM/DD/YYYY inside filename or text
    match = re.search(r'\b(\d{2})[_\/\-](\d{2})[_\/\-](\d{4})\b', date_str)
    if match:
        m, d, y = match.groups()
        try:
            return datetime(int(y), int(m), int(d))
        except ValueError:
            pass

    # Regex search for YYYY
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', date_str)
    if year_match:
        return datetime(int(year_match.group(1)), 1, 1)

    return None

def format_date_abbrev(dt: datetime) -> str:
    """Format datetime as 'Nov 20 2018'"""
    m_name = MONTH_MAP.get(dt.month, dt.strftime("%b"))
    return f"{m_name} {dt.day:02d} {dt.year}"

def calculate_date_range_str(dates: List[datetime]) -> str:
    """
    Given a list of datetimes, calculates oldest date to newest date.
    Example: Nov 20 2018 – Sept 20 2023
    """
    valid_dates = [d for d in dates if d is not None]
    if not valid_dates:
        return "N/A"

    oldest = min(valid_dates)
    newest = max(valid_dates)

    if oldest == newest:
        return format_date_abbrev(oldest)

    return f"{format_date_abbrev(oldest)} – {format_date_abbrev(newest)}"

INVALID_CLIENT_PHRASES = [
    'receive for and on behalf', 'on behalf of', 'authorized to',
    'depose and state', 'duly sworn', 'board of directors',
    'having been', 'whom it may concern', 'open and maintain',
    'filipino', 'legal age', 'duly elected', 'republic of the',
    'know all men', 'subscribed and sworn', 'notary public'
]

def extract_client_name_from_pdf(pdf_path: str) -> str:
    try:
        import fitz
        with fitz.open(pdf_path) as doc:
            if len(doc) > 0:
                text_p1 = doc[0].get_text()
                text_full = '\n'.join([doc[i].get_text() for i in range(min(len(doc), 3))])

                # 1. Corporate Officer Pattern (Secretary, Treasurer, President, etc.)
                OFFICER_ROLES = r'(?:(?:Corporate|Company)\s+Secretary|Secretary|Treasurer|Corporate\s+Treasurer|President|Corporate\s+President|Managing\s+Director|Director|Chairman|Trustee)'
                officer_match = re.search(
                    r'(?:I\s+am\s+the\s+|being\s+the\s+(?:duly\s+)?(?:elected\s+and\s+)?(?:qualified\s+)?|duly\s+(?:elected\s+and\s+)?qualified\s+|elected\s+and\s+qualified\s+|incumbent\s+|being\s+the\s+)?' + OFFICER_ROLES + r'\s+(?:of\s+)?([A-Za-z0-9\s,\.\-&]+?)(?:\s*,\s*\[\s*hereinafter|\s*\[\s*hereinafter|\s*,\s*\(\s*(?:the|hereinafter)|\s*\(\s*(?:the|hereinafter)|\s*,\s*a\s+(?:domestic\s+)?corporation|\s*,\s*after|\s*,\s*with\s+principal|\s*\n\s*\n|\.\s)',
                    text_full,
                    re.IGNORECASE
                )
                if officer_match:
                    raw_cname = officer_match.group(1).strip().rstrip(',').strip()
                    if 3 <= len(raw_cname) <= 80 and not any(k in raw_cname.lower() for k in INVALID_CLIENT_PHRASES):
                        return format_client_name(raw_cname)

                # 2. Known Clients / Direct Header search
                if 'beacon homes' in text_full.lower():
                    return format_client_name("Beacon Homes Development Corporation")
                if 'zenith realty' in text_full.lower():
                    return format_client_name("Zenith Realty Development Corp.")


                # 3. TO / Attention / Client line (Require line start & colon to prevent matching "to <verb>")
                to_match = re.search(r'(?:^|\n)\s*(?:ATTENTION|ATTN|CLIENT)\s*:\s*([A-Za-z0-9\s,\.\-&]{3,60})', text_p1, re.IGNORECASE)
                if not to_match:
                    to_match = re.search(r'(?:^|\n)\s*TO\s*:\s*([A-Za-z0-9\s,\.\-&]{3,60})', text_p1)
                if to_match:
                    cleaned = to_match.group(1).strip().split('\n')[0].strip()
                    if len(cleaned) >= 3 and not any(k in cleaned.lower() for k in INVALID_CLIENT_PHRASES):
                        return format_client_name(cleaned)

                # 4. Summary of Services Rendered for <Client>
                sos_match = re.search(r'Services\s+Rendered\s+for\s+([A-Z0-9\s,\.\-&]{4,60})', text_full, re.IGNORECASE)
                if sos_match:
                    cleaned = sos_match.group(1).strip().split('\n')[0].strip()
                    if not any(k in cleaned.lower() for k in INVALID_CLIENT_PHRASES):
                        return format_client_name(cleaned)

    except Exception as e:
        logger.debug(f"Error extracting client name from {pdf_path}: {e}")

    return "General Clients"

def update_clients_docx(docx_path: str, client_name: str, date_range_str: str) -> None:
    """
    Creates or updates Clients.docx containing a 2-column table: [Name | Date Range].
    Fills empty rows in template tables if available before adding new rows.
    """
    client_name = format_client_name(client_name)
    os.makedirs(os.path.dirname(os.path.abspath(docx_path)), exist_ok=True)

    if os.path.exists(docx_path):
        try:
            doc = Document(docx_path)
        except Exception as e:
            logger.warning(f"Could not open existing {docx_path}, creating new: {e}")
            doc = Document()
    else:
        doc = Document()

    table = None
    if len(doc.tables) > 0:
        table = doc.tables[0]

    if table is None:
        if len(doc.paragraphs) == 0 or not doc.paragraphs[0].text:
            heading = doc.add_heading("Client Summary Index", level=1)
            heading.alignment = WD_ALIGN_PARAGRAPH.LEFT

        table = doc.add_table(rows=1, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Name"
        hdr_cells[1].text = "Date Range"

        for cell in hdr_cells:
            for p in cell.paragraphs:
                for run in p.runs:
                    run.font.bold = True
                    run.font.size = Pt(11)

    client_row = None
    first_empty_row = None

    for row in table.rows[1:]:
        if len(row.cells) >= 2:
            cell_name = row.cells[0].text.strip()
            if cell_name.lower() == client_name.strip().lower():
                client_row = row
                break
            elif not cell_name and first_empty_row is None:
                first_empty_row = row

    if client_row is not None:
        client_row.cells[0].text = client_name
        client_row.cells[1].text = date_range_str
        logger.info(f"Updated row in Clients.docx for '{client_name}': {date_range_str}")
    elif first_empty_row is not None:
        first_empty_row.cells[0].text = client_name
        first_empty_row.cells[1].text = date_range_str
        logger.info(f"Populated empty row in Clients.docx for '{client_name}': {date_range_str}")
    else:
        row_cells = table.add_row().cells
        row_cells[0].text = client_name
        row_cells[1].text = date_range_str
        logger.info(f"Appended new row to Clients.docx for '{client_name}': {date_range_str}")

    doc.save(docx_path)
    logger.info(f"Successfully saved {docx_path}")

class ClientManager:
    """
    Manages grouping files by Client Name, moving them to client directories outside Temporary,
    calculating date ranges, and updating Clients.docx.
    """
    def __init__(self, base_watch_dir: str, update_docx: bool = False):
        abs_watch = os.path.abspath(base_watch_dir)
        path_parts = abs_watch.split(os.sep)
        if "Temporary" in path_parts:
            temp_idx = path_parts.index("Temporary")
            self.root_dir = os.sep.join(path_parts[:temp_idx])
            self.temp_dir = os.sep.join(path_parts[:temp_idx + 1])
        else:
            self.root_dir = os.path.dirname(abs_watch)
            self.temp_dir = abs_watch

        if not self.root_dir:
            self.root_dir = abs_watch

        self.docx_path = os.path.join(self.root_dir, "Clients.docx")
        self.update_docx = update_docx
        self.active_client: Optional[str] = None
        self._lock = threading.Lock()

    def resolve_client_name(self, extracted_name: Optional[str]) -> Tuple[str, bool]:
        """
        Resolves client name using extracted metadata or carries over previous active client.
        Returns (client_name, is_inherited).
        """
        with self._lock:
            clean_name = str(extracted_name).strip() if extracted_name else ""
            if clean_name and clean_name.lower() not in ("general clients", "none", "null", "unrecognized", ""):
                formatted = format_client_name(clean_name)
                self.active_client = formatted
                return formatted, False

            # If no client name extracted, inherit active client if available
            if self.active_client:
                return self.active_client, True

            return "General Clients", False

    def set_active_client(self, client_name: str) -> None:
        with self._lock:
            self.active_client = format_client_name(client_name)

    def get_active_client(self) -> Optional[str]:
        with self._lock:
            return self.active_client

    def reset_active_client(self) -> None:
        with self._lock:
            self.active_client = None

    def route_file_to_client(
        self,
        src_file: str,
        client_name: str,
        doc_date: Optional[str] = None,
        target_filename: Optional[str] = None
    ) -> str:
        """
        Directly moves file into the client directory (<root_dir>/<client_name>/),
        resolving any filename collisions and updating Clients.docx date range.
        Returns the final destination file path.
        """
        client_name = format_client_name(client_name)
        client_dir = os.path.join(self.root_dir, client_name)
        os.makedirs(client_dir, exist_ok=True)

        filename = target_filename or os.path.basename(src_file)
        final_name, dest_path = resolve_filename_collision(client_dir, filename, src_file)

        # Move the file with retry for transient Windows file locks
        moved = False
        for attempt in range(4):
            try:
                shutil.move(src_file, dest_path)
                moved = True
                break
            except PermissionError:
                time.sleep(0.3)

        if not moved:
            shutil.move(src_file, dest_path)

        logger.info(f"[Direct Routing] Successfully routed '{os.path.basename(src_file)}' -> '{client_name}/{final_name}'")

        # Update Clients.docx only if explicitly enabled
        if self.update_docx:
            doc_dates: List[datetime] = []
            if os.path.exists(client_dir):
                for existing_file in os.listdir(client_dir):
                    ex_path = os.path.join(client_dir, existing_file)
                    if os.path.isfile(ex_path) and existing_file.lower().endswith('.pdf'):
                        dt_ex = parse_date_to_dt(existing_file)
                        if dt_ex:
                            doc_dates.append(dt_ex)

            date_str = doc_date or final_name
            dt = parse_date_to_dt(date_str)
            if dt and dt not in doc_dates:
                doc_dates.append(dt)

            date_range_str = calculate_date_range_str(doc_dates)
            try:
                update_clients_docx(self.docx_path, client_name, date_range_str)
            except Exception as e:
                logger.error(f"Error updating Clients.docx for '{client_name}': {e}")

        return dest_path

    def wrap_up_batch(self, processed_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Scans Temporary folder & processed records, groups files by client_name,
        creates Title Case Client folders outside Temporary, moves files, calculates date ranges,
        and updates Clients.docx.
        """
        all_records = list(processed_records) if processed_records else []
        seen_paths = {r.get("file_path") for r in all_records if r.get("file_path")}

        # Also scan Temporary directory & subfolders for any files waiting inside Temporary
        if os.path.exists(self.temp_dir):
            for root, _, files in os.walk(self.temp_dir):
                for fname in files:
                    if fname.lower() in ('wrap.txt', 'done.txt', '.wrap', 'wrapup.txt', 'wrap', '.ds_store'):
                        continue
                    if fname.startswith('.'):
                        continue
                    fpath = os.path.join(root, fname)
                    if os.path.isfile(fpath) and fpath not in seen_paths:
                        c_name = extract_client_name_from_pdf(fpath) if fname.lower().endswith('.pdf') else "General Clients"
                        all_records.append({
                            "file_path": fpath,
                            "filename": fname,
                            "client_name": c_name,
                            "doc_date": fname
                        })
                        seen_paths.add(fpath)

        if not all_records:
            logger.info(f"No processed files found in '{self.temp_dir}' or records to wrap up.")
            return []

        client_groups: Dict[str, List[Dict[str, Any]]] = {}
        for record in all_records:
            c_name = record.get("client_name")
            if not c_name and record.get("file_path"):
                c_name = extract_client_name_from_pdf(record["file_path"])
            c_name = format_client_name(c_name)
            client_groups.setdefault(c_name, []).append(record)

        summary_results = []

        for client_name, records in client_groups.items():
            client_dir = os.path.join(self.root_dir, client_name)
            os.makedirs(client_dir, exist_ok=True)

            doc_dates: List[datetime] = []
            moved_files: List[str] = []

            # Include dates from existing files in client_dir
            if os.path.exists(client_dir):
                for existing_file in os.listdir(client_dir):
                    ex_path = os.path.join(client_dir, existing_file)
                    if os.path.isfile(ex_path) and existing_file.lower().endswith('.pdf'):
                        dt_ex = parse_date_to_dt(existing_file)
                        if dt_ex:
                            doc_dates.append(dt_ex)

            for rec in records:
                src_file = rec.get("file_path")
                filename = rec.get("filename") or (os.path.basename(src_file) if src_file else "document.pdf")
                
                date_str = rec.get("doc_date") or filename
                dt = parse_date_to_dt(date_str)
                if dt:
                    doc_dates.append(dt)

                if src_file and os.path.exists(src_file):
                    filename, dest_file = resolve_filename_collision(client_dir, filename, src_file)

                    try:
                        shutil.move(src_file, dest_file)
                        moved_files.append(dest_file)
                        logger.info(f"Moved file from Temporary to Client directory: '{src_file}' -> '{dest_file}'")
                    except Exception as e:
                        logger.error(f"Error moving file '{src_file}' to '{dest_file}': {e}")

            date_range_str = calculate_date_range_str(doc_dates)
            if self.update_docx:
                update_clients_docx(self.docx_path, client_name, date_range_str)

            summary_results.append({
                "client_name": client_name,
                "client_dir": client_dir,
                "date_range": date_range_str,
                "moved_files": moved_files
            })

        return summary_results

