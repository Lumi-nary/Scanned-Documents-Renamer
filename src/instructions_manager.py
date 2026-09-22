import os
import json
import logging
import copy
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_ROLE = """You are an automated document vision & OCR assistant for scanning and classifying files.
Visually inspect the DOCUMENT IMAGE provided to accurately identify the main Document Title/Header, Subject/Re line, and relevant dates or reference numbers."""

DEFAULT_CLIENT_RULES = """1. Corporate Officer & Secretary Pattern:
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
     * "ATLAS PHARMACEUTICALS, INC." -> "Atlas Pharmaceuticals, Inc.\""""

DEFAULT_FORMATTING_RULES = """Respond ONLY with a single raw JSON object containing "filename", "client_name", and "doc_date" keys.
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
{"filename": "Unrecognized.pdf", "client_name": null, "doc_date": null}"""

PRESET_FILE_TYPES: List[Dict[str, Any]] = [
    {
        "id": "liquidation_of_deposit",
        "name": "Liquidation of Deposit",
        "is_preset": True,
        "enabled": True,
        "priority": 1,
        "match_keywords": ["Liquidation of Deposit", "Accounting of Deposit"],
        "naming_format": "Liquidation of Deposit for Out-of-Pocket Expenses MM_DD_YYYY.pdf",
        "instructions": """- Check if header/title or Subject/Re line contains "Liquidation of Deposit" or "Accounting of Deposit".
- CRITICAL: "Liquidation of Deposit" takes HIGHER PRIORITY over Rule 2 (Statement of Account / OPE). Do NOT classify "Liquidation of Deposit" under Statement of Account / OPE, and do NOT strip the document title to numbers-only!
- Format: "Liquidation of Deposit for Out-of-Pocket Expenses MM_DD_YYYY.pdf" (e.g. "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf")."""
    },
    {
        "id": "statement_of_account",
        "name": "Statement of Account / SOA / Out-of-Pocket Expenses (OPE)",
        "is_preset": True,
        "enabled": True,
        "priority": 2,
        "match_keywords": ["Statement of Account", "SOA", "Out-of-Pocket Expenses", "OPE"],
        "naming_format": "<NUMBERS>.pdf (e.g. 13656.pdf, 20220129.pdf)",
        "instructions": """- Check if the main header/title (especially on Page 1) contains "Statement of Account", "SOA", or standalone "Out-of-Pocket Expenses" / "OPE" (excluding "Liquidation of Deposit"). This rule ALWAYS takes top priority over attached inner pages (e.g. "Summary of Services Rendered").
- Look for Statement of Account / SOA number, 5-digit statement numbers, or OPE reference number (e.g. "No. 13656", "13656", "No. 2022-0129", "No. OPE-1185", "OPE-1185", "SOA-2022-0540", etc.).
- Extract ONLY the numerical digits of the SOA, 5-digit statement number, or OPE number (e.g. "No. 13656" -> "13656.pdf", "No. 2022-0129" -> "20220129.pdf", "OPE-1185" -> "1185.pdf").
- CRITICAL: When the document shows "No. 13656" or any 5-digit/4-digit number at the top or bottom of a Statement of Account, extract those digits directly to rename the file (e.g. "13656.pdf").
- CRITICAL: SOA numbers often start with a year prefix followed by a hyphen or space (e.g. "2022-0129", "2022-0540"). This is a Statement Reference Number ("20220129"), NOT a date! Do NOT mistake "2022-0129" for a date, and do NOT use the document date (e.g. "February 24, 2022") to rename Statement of Account files.
- HANDWRITING & PEN INSTRUCTIONS: Carefully read BOTH printed numbers AND any pen-written/handwritten digits next to it (e.g., if "2022-" is printed and "0540" is written by pen next to it, the full number is "20220540"). Do NOT ignore handwritten numbers.
- STRICT RULE: STOP renaming SOA files with the text "Statement of Account" or document dates. The filename MUST BE JUST NUMBERS: "<NUMBERS>.pdf" (e.g. "13656.pdf", "20220129.pdf", "1185.pdf", or "20220540.pdf").
- IMPORTANT: DO NOT include words like "Statement of Account", "SOA", "Out-of-Pocket Expenses", or prefix letters like "OPE-" in the filename under any circumstances for SOA/OPE files. Output numerical digits ONLY."""
    },
    {
        "id": "transmittal_sheet",
        "name": "Transmittal Sheet",
        "is_preset": True,
        "enabled": True,
        "priority": 3,
        "match_keywords": ["Transmittal Sheet"],
        "naming_format": "Transmittal Sheet MM_DD_YYYY.pdf",
        "instructions": """- ONLY classify as Transmittal Sheet if the document explicitly has "Transmittal Sheet" written in its title/header.
- Read the primary transmittal date in numerical format MM_DD_YYYY (e.g. "January 8, 2024" -> "01_08_2024").
- Format: "Transmittal Sheet MM_DD_YYYY.pdf" (e.g. "Transmittal Sheet 01_08_2024.pdf")."""
    },
    {
        "id": "summary_of_services",
        "name": "Summary of Services / Services Rendered",
        "is_preset": True,
        "enabled": True,
        "priority": 4,
        "match_keywords": ["Summary of Services Rendered", "Summary of Services", "Services Rendered"],
        "naming_format": "Summary of Services <Period>.pdf",
        "instructions": """- Check if header/title contains "Summary of Services Rendered", "Summary of Services", or "Services Rendered".
- Read the date range or period visually (e.g. "May to August 2018", "February to June 2019", "October 2022 to March 2023").
- MUST format filename strictly as: "Summary of Services <Period>.pdf" (e.g. "Summary of Services May to August 2018.pdf", "Summary of Services February to June 2019.pdf").
- STRICT RULE: Do NOT include subject prefix words like "Litigation -", "Retainer -", client names, or any extra text between "Summary of Services" and the period! Output strictly "Summary of Services <Period>.pdf" (e.g. "Summary of Services May to August 2018.pdf", NOT "Summary of Services Litigation - May to August 2018.pdf").
- Do NOT use handwritten dates (e.g. "9-17-18") when a period range like "May to August 2018" is printed on the document."""
    },
    {
        "id": "corporate_certificates",
        "name": "Corporate Certificates (Secretary's Certificate, Doc. No., Notarial)",
        "is_preset": True,
        "enabled": True,
        "priority": 5,
        "match_keywords": ["Secretary's Certificate", "Certification of Capital Investment", "Treasurer's Certificate"],
        "naming_format": "<Exact_Certificate_Title> Doc. No. <Doc_No>.pdf",
        "instructions": """- Check the document title/header on Page 1 (e.g. "Secretary's Certificate", "Certification of Capital Investment", "Treasurer's Certificate").
- Check the notarial acknowledgment section (which may appear on Page 1 or on the LAST / signature page, and in any zoomed-in close-up crop) for "Doc. No:" / "Doc. No.:".
- CRITICAL HANDWRITING & DIGIT DISCRIMINATION INSTRUCTIONS:
  * Carefully inspect the pen-written / handwritten number next to "Doc. No:" / "Doc. No.:" on the signature page or zoomed notary crop.
  * Distinguish each handwritten digit with extreme care based on its stroke anatomy (4 vs 7/9, 5 vs 0/8/9, etc.).
- If "Doc. No:" with a document number is found, ALWAYS format the filename strictly using the EXACT document title as: "<Exact_Certificate_Title> Doc. No. <Doc_No>.pdf"
  (e.g. "Secretary's Certificate Doc. No. 384.pdf", "Certification of Capital Investment Doc. No. 320.pdf").
- If NO Doc. No. is found, use the Document Title followed by the date found on the first page in MM_DD_YYYY format (e.g. "Certification of Capital Investment 08_18_2025.pdf").
- EXEMPTION TO 1-PAGE RULE: Notarized Corporate Certificates are explicitly EXEMPT from the hard 1-page restriction specifically for extracting "Doc. No." and notarial acknowledgment details that appear on the last / signature page."""
    },
    {
        "id": "statutory_certificates",
        "name": "Registration Documents & Authority (SEC, BIR Form 2303, ATP, BIR 1903)",
        "is_preset": True,
        "enabled": True,
        "priority": 6,
        "match_keywords": ["Certificate of Incorporation", "Certificate of Registration", "Authority to Print", "Application for Registration", "BIR Form 1903", "BIR Form 2303", "BIR Form 1906"],
        "naming_format": "Certificate of Incorporation <REG_NO>.pdf / Certificate of Registration <OCN>.pdf / Application for Registration <TIN>.pdf",
        "instructions": """- For "Certificate of Incorporation":
  * Look for "COMPANY REG. NO." or SEC Registration Number on Page 1 (e.g. "COMPANY REG. NO.: 2025030195697-02").
  * ALWAYS format filename as: "Certificate of Incorporation <COMPANY_REG_NO>.pdf".
- For "Certificate of Registration" (BIR Form 2303):
  * Look for the "OCN" (Order Confirmation Number) on Page 1.
  * ALWAYS format filename as: "Certificate of Registration <OCN_NUMBER>.pdf".
- For "Authority to Print" / "ATP" (BIR Form 1906):
  * Look for the "OCN" on Page 1. Format as "Authority to Print <OCN_NUMBER>.pdf".
- For "Application for Registration" (BIR Form 1903, 1901, etc.):
  * Look for the "TIN" (Taxpayer Identification Number) at the top box or in Part I of Page 1.
  * Filename MUST be strictly: "Application for Registration <TIN>.pdf".
  * Client name MUST be strictly just the Registered/Trade Business Name.
- STRICT CRITICAL RULE: ONLY use registration number, OCN, TIN, or date from the FIRST PAGE."""
    },
    {
        "id": "tax_declarations",
        "name": "Tax Returns & Declarations (Doc Stamp BIR 2000, 2000-OT)",
        "is_preset": True,
        "enabled": True,
        "priority": 7,
        "match_keywords": ["Monthly Documentary Stamp Tax Declaration Return", "Declaration/Return", "Declaration Return"],
        "naming_format": "<Document_Title> MM_YYYY.pdf",
        "instructions": """- For titles with slashes like "Declaration/Return" (e.g. "Monthly Documentary Stamp Tax Declaration/Return", BIR Form 2000, 2000-OT):
  * NEVER use slashes "/" in filenames. Replace slashes with a space so it is "Declaration Return".
  * Format: "<Document_Title> MM_YYYY.pdf" or "<Document_Title> MM_DD_YYYY.pdf" (e.g. "Monthly Documentary Stamp Tax Declaration Return 08_2025.pdf")."""
    },
    {
        "id": "subject_re_documents",
        "name": "Documents with Subject or 'Re:' Line (Proposals, Letters)",
        "is_preset": True,
        "enabled": True,
        "priority": 8,
        "match_keywords": ["Re:", "Re :", "Subject:"],
        "naming_format": "<Subject_Title> MM_DD_YYYY.pdf",
        "instructions": """- Locate the "Re:" or Subject line on the document image (e.g. "Re : Retainer Services Proposal").
- Extract the main title, ignoring "Re:" or "Re :" (e.g. "Retainer Services Proposal").
- Read the document date and convert it to numerical format MM_DD_YYYY (e.g., "September 22, 2017" -> "09_22_2017").
- Format MUST use a space, NOT a trailing underscore after the title: "<Subject_Title> MM_DD_YYYY.pdf" (e.g. "Retainer Services Proposal 09_22_2017.pdf")."""
    },
    {
        "id": "other_documents",
        "name": "Other Standard Documents (Invoices, Receipts, Contracts, Reports)",
        "is_preset": True,
        "enabled": True,
        "priority": 9,
        "match_keywords": ["Invoice", "Receipt", "Contract", "Agreement", "Report"],
        "naming_format": "<Document_Title> MM_DD_YYYY.pdf",
        "instructions": """- Read actual title/header + numerical date MM_DD_YYYY.
- Format with spaces, no underscores between Title and Date: "<Document_Title> MM_DD_YYYY.pdf"."""
    },
    {
        "id": "unrecognized_documents",
        "name": "Unrecognized / Untitled / Unidentified Documents",
        "is_preset": True,
        "enabled": True,
        "priority": 10,
        "match_keywords": [],
        "naming_format": "Unrecognized.pdf",
        "instructions": """- If the scanned document has NO clear document title/header, or is an arbitrary table/form/list, sign-in sheet, attendance log, roster, draft, attachment, or unidentified document:
- CRITICAL: DO NOT hallucinate, guess, or invent document titles or client names.
- ALWAYS name the file strictly: "Unrecognized.pdf".
- Set "client_name": null (the pipeline will automatically route it to the active client folder).
- Set "doc_date": null (or the visible document date formatted as MM/DD/YYYY if present)."""
    }
]


class InstructionsManager:
    """
    Manages user-customizable document classification instructions.
    Loads and persists rules to instructions.json, and compiles them into
    the multimodal AI system prompt or deterministic native rules.
    """
    def __init__(self, instructions_file: str = "instructions.json"):
        self.instructions_file = instructions_file
        self.system_role: str = DEFAULT_SYSTEM_ROLE
        self.client_rules: str = DEFAULT_CLIENT_RULES
        self.formatting_rules: str = DEFAULT_FORMATTING_RULES
        self.file_types: List[Dict[str, Any]] = copy.deepcopy(PRESET_FILE_TYPES)
        self.load()

    def load(self) -> None:
        """Loads instructions from file if present, else initializes with preset defaults."""
        if os.path.exists(self.instructions_file):
            try:
                with open(self.instructions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if "global_instructions" in data and isinstance(data["global_instructions"], dict):
                    globals_dict = data["global_instructions"]
                    if "system_role" in globals_dict:
                        self.system_role = globals_dict["system_role"]
                    if "client_rules" in globals_dict:
                        self.client_rules = globals_dict["client_rules"]
                    if "formatting_rules" in globals_dict:
                        self.formatting_rules = globals_dict["formatting_rules"]

                if "file_types" in data and isinstance(data["file_types"], list):
                    # Validate and preserve structure
                    loaded_types = []
                    for item in data["file_types"]:
                        if isinstance(item, dict) and "name" in item:
                            loaded_types.append({
                                "id": str(item.get("id") or item["name"].lower().replace(" ", "_")),
                                "name": str(item.get("name", "")).strip(),
                                "is_preset": bool(item.get("is_preset", False)),
                                "enabled": bool(item.get("enabled", True)),
                                "priority": int(item.get("priority", len(loaded_types) + 1)),
                                "match_keywords": list(item.get("match_keywords", [])),
                                "naming_format": str(item.get("naming_format", "")).strip(),
                                "instructions": str(item.get("instructions", "")).strip()
                            })
                    if loaded_types:
                        self.file_types = loaded_types
                        logger.info(f"Loaded {len(self.file_types)} document instructions from {self.instructions_file}")
                        return
            except Exception as e:
                logger.warning(f"Error loading {self.instructions_file}: {e}. Using defaults.")

        # If file does not exist, save preset defaults immediately
        self.save()

    def save(self) -> None:
        """Persists current instructions to JSON file."""
        data = self.to_dict()
        try:
            with open(self.instructions_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved document instructions to {self.instructions_file}")
        except Exception as e:
            logger.error(f"Failed to save document instructions to {self.instructions_file}: {e}")

    def reset_to_defaults(self) -> None:
        """Resets instructions back to preset defaults and persists."""
        self.system_role = DEFAULT_SYSTEM_ROLE
        self.client_rules = DEFAULT_CLIENT_RULES
        self.formatting_rules = DEFAULT_FORMATTING_RULES
        self.file_types = copy.deepcopy(PRESET_FILE_TYPES)
        self.save()
        logger.info("Reset document instructions to preset defaults.")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes instructions to dictionary."""
        return {
            "version": "1.0",
            "global_instructions": {
                "system_role": self.system_role,
                "client_rules": self.client_rules,
                "formatting_rules": self.formatting_rules
            },
            "file_types": self.file_types
        }

    def update_instructions(self, payload: Dict[str, Any]) -> None:
        """
        Updates file types and/or global instructions from a dictionary payload and persists to disk.
        """
        if "global_instructions" in payload and isinstance(payload["global_instructions"], dict):
            g = payload["global_instructions"]
            if "system_role" in g and isinstance(g["system_role"], str):
                self.system_role = g["system_role"].strip()
            if "client_rules" in g and isinstance(g["client_rules"], str):
                self.client_rules = g["client_rules"].strip()
            if "formatting_rules" in g and isinstance(g["formatting_rules"], str):
                self.formatting_rules = g["formatting_rules"].strip()

        if "file_types" in payload and isinstance(payload["file_types"], list):
            new_types = []
            for i, item in enumerate(payload["file_types"]):
                if isinstance(item, dict) and item.get("name"):
                    rule_id = str(item.get("id") or f"custom_{i+1}")
                    new_types.append({
                        "id": rule_id,
                        "name": str(item.get("name", "")).strip(),
                        "is_preset": bool(item.get("is_preset", False)),
                        "enabled": bool(item.get("enabled", True)),
                        "priority": int(item.get("priority", i + 1)),
                        "match_keywords": [str(k).strip() for k in item.get("match_keywords", []) if str(k).strip()],
                        "naming_format": str(item.get("naming_format", "")).strip(),
                        "instructions": str(item.get("instructions", "")).strip()
                    })
            self.file_types = new_types

        self.save()

    def get_system_prompt(self) -> str:
        """
        Dynamically compiles the full classification system prompt using active file types
        and global formatting rules.
        """
        sections = []

        # 1. Base Role
        if self.system_role:
            sections.append(self.system_role.strip())

        # 2. Categorization Rules
        active_rules = sorted(
            [r for r in self.file_types if r.get("enabled", True)],
            key=lambda x: x.get("priority", 999)
        )

        rules_text = ["CATEGORIZATION RULES:\n"]
        for idx, rule in enumerate(active_rules, start=1):
            rule_header = f"{idx}. {rule['name']}:"
            body_parts = []
            if rule.get("match_keywords"):
                keywords_str = ", ".join([f'"{k}"' for k in rule["match_keywords"]])
                body_parts.append(f"   - Match keywords / headers: {keywords_str}")
            if rule.get("naming_format"):
                body_parts.append(f"   - Target filename pattern: {rule['naming_format']}")
            if rule.get("instructions"):
                # Indent instructions properly if needed
                inst_lines = rule["instructions"].splitlines()
                for line in inst_lines:
                    if line.strip():
                        if line.startswith("   ") or line.startswith("\t"):
                            body_parts.append(line)
                        elif line.startswith("-") or line.startswith("*"):
                            body_parts.append(f"   {line}")
                        else:
                            body_parts.append(f"   - {line}")
            rules_text.append(rule_header)
            if body_parts:
                rules_text.append("\n".join(body_parts))
            rules_text.append("")

        sections.append("\n".join(rules_text).strip())

        # 3. Client Rules
        if self.client_rules:
            sections.append(f"CLIENT / CORPORATE NAME EXTRACTION & FORMATTING RULES:\n{self.client_rules.strip()}")

        # 4. Critical Output & Formatting Rules
        if self.formatting_rules:
            sections.append(f"CRITICAL REQUIREMENT:\n{self.formatting_rules.strip()}")

        return "\n\n".join(sections) + "\n"

    def match_custom_rule_native(self, text_p1: str, text_full: str, file_basename: str) -> Optional[str]:
        """
        Evaluates active user-defined rules for offline native matching.
        Returns a suggested filename if a custom rule matches with high confidence.
        """
        combined = f"{file_basename} {text_p1} {text_full}".lower()
        active_custom = [
            r for r in self.file_types 
            if r.get("enabled", True) and not r.get("is_preset", False)
        ]
        active_custom = sorted(active_custom, key=lambda x: x.get("priority", 999))

        for rule in active_custom:
            keywords = [k.lower() for k in rule.get("match_keywords", []) if k.strip()]
            if not keywords:
                continue
            # If all or any of keywords match
            if any(k in combined for k in keywords):
                naming = rule.get("naming_format", "").strip()
                if naming:
                    return naming
                return f"{rule['name']}.pdf"

        return None


# Global singleton instance
_instructions_manager: Optional[InstructionsManager] = None

def get_instructions_manager(instructions_file: Optional[str] = None) -> InstructionsManager:
    global _instructions_manager
    if _instructions_manager is None:
        _instructions_manager = InstructionsManager(instructions_file=instructions_file or "instructions.json")
    elif instructions_file and _instructions_manager.instructions_file != instructions_file:
        _instructions_manager.instructions_file = instructions_file
        _instructions_manager.load()
    return _instructions_manager
