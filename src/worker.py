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
from src.organizer import classify_pdf_by_rules, resolve_filename_collision, extract_date_from_text
from src.client_manager import format_client_name, extract_client_name_from_pdf, INVALID_CLIENT_PHRASES
from src.instructions_manager import get_instructions_manager

logger = logging.getLogger(__name__)

# Default prompt initialized dynamically from InstructionsManager
CLASSIFICATION_SYSTEM_PROMPT = get_instructions_manager().get_system_prompt()


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

            # Step 2: Read payload & Extract Metadata (Native Mode or AI Provider)
            ai_target_name = None
            extracted_client_name = None
            extracted_doc_date = None
            pdf_p1_text = ""
            pdf_full_text = ""

            if file_path.lower().endswith('.pdf'):
                try:
                    from src.ocr_engine import extract_pdf_pages_text
                    pdf_p1_text, pdf_full_text = extract_pdf_pages_text(file_path)
                except Exception as e:
                    logger.debug(f"Error reading PDF text: {e}")

            if getattr(config, 'provider', 'native') == "native":
                logger.info(f"[{thread_name}] Processing in Native Mode (100% Offline / Local PP-OCR). Note: Native OCR may have inaccuracies on degraded scans; an AI API is recommended for highest precision.")
                if file_path.lower().endswith('.pdf'):
                    known = client_mgr.get_client_directories() if client_mgr else None
                    inst_mgr = get_instructions_manager()
                    custom_native_match = inst_mgr.match_custom_rule_native(pdf_p1_text, pdf_full_text, os.path.basename(file_path))
                    if custom_native_match:
                        ai_target_name = custom_native_match
                    else:
                        ai_target_name = classify_pdf_by_rules(file_path, text_p1=pdf_p1_text, text_full=pdf_full_text)
                    extracted_client_name = extract_client_name_from_pdf(
                        file_path, text_p1=pdf_p1_text, text_full=pdf_full_text, known_clients=known
                    )
                    extracted_doc_date = (
                        extract_date_from_text(pdf_p1_text)
                        or extract_date_from_text(pdf_full_text)
                        or extract_date_from_text(os.path.basename(file_path))
                    )

                    # Second-pass fallback: If initial classification or client matching resulted in Unrecognized or General Clients,
                    # force local PP-OCR to ensure high-accuracy offline extraction
                    if (not ai_target_name or ai_target_name.lower().startswith("unrecognized") or extracted_client_name == "General Clients"):
                        try:
                            from src.ocr_engine import extract_pdf_pages_text
                            ocr_p1, ocr_full = extract_pdf_pages_text(file_path, force_ocr=True)
                            if ocr_p1 and ocr_p1.strip():
                                custom_ocr_match = inst_mgr.match_custom_rule_native(ocr_p1, ocr_full, os.path.basename(file_path))
                                if custom_ocr_match:
                                    ocr_target = custom_ocr_match
                                else:
                                    ocr_target = classify_pdf_by_rules(file_path, text_p1=ocr_p1, text_full=ocr_full)
                                if ocr_target and not ocr_target.lower().startswith("unrecognized"):
                                    ai_target_name = ocr_target
                                    pdf_p1_text = ocr_p1
                                    pdf_full_text = ocr_full
                                ocr_client = extract_client_name_from_pdf(
                                    file_path, text_p1=ocr_p1, text_full=ocr_full, known_clients=known
                                )
                                if ocr_client and ocr_client != "General Clients":
                                    extracted_client_name = ocr_client
                                    pdf_p1_text = ocr_p1
                                    pdf_full_text = ocr_full
                                if not extracted_doc_date:
                                    extracted_doc_date = extract_date_from_text(ocr_p1) or extract_date_from_text(ocr_full)
                        except Exception as ocr_err:
                            logger.debug(f"PP-OCR second-pass fallback error: {ocr_err}")

                    logger.info(f"[{thread_name}] Native Engine classified target: '{ai_target_name}' (Client: '{extracted_client_name}')")
            else:
                # Technical User Mode: Local LLM (Ollama / LM Studio) or Cloud API
                try:
                    response = None
                    active_system_prompt = get_instructions_manager().get_system_prompt()
                    if file_path.lower().endswith('.pdf'):
                        b64_imgs = pdf_to_base64_images(file_path)
                        if b64_imgs:
                            logger.info(f"[{thread_name}] Dispatching {len(b64_imgs)} visual document page(s) to AI Model ({config.model_name})...")
                            
                            p1_excerpt = pdf_p1_text[:1500].strip() if pdf_p1_text else ""
                            prompt_text = "Perform visual AI OCR on this document image (including first and last/signature pages and zoomed notary crop). Read all dates, numbers, headers, Doc. No., and client names visually and return the metadata JSON."
                            if p1_excerpt:
                                prompt_text = f"Document text excerpt from Page 1:\n---\n{p1_excerpt}\n---\n\n{prompt_text}"

                            response = api_dispatcher.dispatch_vision(
                                image_b64_url=b64_imgs,
                                system_prompt=active_system_prompt,
                                text_prompt=prompt_text
                            )

                    if not response:
                        # Text prompt fallback (for text-only local models or non-PDF files)
                        content = pdf_full_text if pdf_full_text else ""
                        if not content and os.path.exists(file_path):
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                content = f.read()
                        if content.strip():
                            response = api_dispatcher.dispatch_prompt(
                                prompt_text=content[:config.max_payload_length],
                                system_prompt=active_system_prompt
                            )

                    if response:
                        metadata = parse_ai_suggested_metadata(response)
                        ai_target_name = metadata.get("filename")
                        extracted_client_name = metadata.get("client_name")
                        extracted_doc_date = metadata.get("doc_date")

                        if ai_target_name:
                            logger.info(f"[{thread_name}] AI classified target filename: '{ai_target_name}'")

                        if output_dir:
                            os.makedirs(output_dir, exist_ok=True)
                            out_filename = f"{os.path.basename(file_path)}.response.txt"
                            out_path = os.path.join(output_dir, out_filename)
                            with open(out_path, 'w', encoding='utf-8') as out_f:
                                out_f.write(response)
                            logger.info(f"[{thread_name}] Saved AI response to: {out_path}")
                except Exception as e:
                    logger.error(f"[{thread_name}] Error processing document with AI model: {e}", exc_info=True)

            # Step 3: Direct routing to Client directory with sticky client context
            file_name = os.path.basename(file_path)

            if ai_target_name and not ai_target_name.lower().startswith("unrecognized"):
                target_name = ai_target_name
            elif file_name.lower().endswith('.pdf'):
                rule_name = classify_pdf_by_rules(file_path, text_p1=pdf_p1_text, text_full=pdf_full_text)
                if rule_name and not rule_name.lower().startswith("unrecognized"):
                    target_name = rule_name
                else:
                    target_name = file_name
            else:
                target_name = file_name

            # Authoritative client extraction & validation from PDF ground-truth text layer
            if file_path.lower().endswith('.pdf'):
                known = client_mgr.get_client_directories() if client_mgr else None
                rule_client = extract_client_name_from_pdf(
                    file_path, text_p1=pdf_p1_text, text_full=pdf_full_text, known_clients=known
                )
                if rule_client and rule_client.lower() != "general clients" and not any(k in rule_client.lower() for k in INVALID_CLIENT_PHRASES):
                    is_bank = any(b in (extracted_client_name or '').lower() for b in ['bank', 'unibank', 'bdo unibank', 'bdo leasing'])
                    
                    pdf_txt = (pdf_full_text or '').lower()
                    ai_client_str = (extracted_client_name or '').lower()
                    ai_words = [w for w in re.sub(r'[^a-z0-9\s]', ' ', ai_client_str).split() if len(w) > 3]
                    ai_not_in_doc = bool(extracted_client_name and ai_words and not any(w in pdf_txt for w in ai_words))
                    ai_is_invalid_phrase = any(k in ai_client_str for k in INVALID_CLIENT_PHRASES)

                    if not extracted_client_name or is_bank or ai_not_in_doc or ai_is_invalid_phrase or (rule_client.lower() in pdf_txt and ai_client_str != rule_client.lower()):
                        logger.info(f"[{thread_name}] Setting client to verified issuing entity from PDF text: '{rule_client}' (AI suggested: '{extracted_client_name}')")
                        extracted_client_name = rule_client

            if not extracted_doc_date and file_path.lower().endswith('.pdf'):
                extracted_doc_date = (
                    extract_date_from_text(pdf_p1_text)
                    or extract_date_from_text(pdf_full_text)
                    or extract_date_from_text(file_name)
                )

            if client_mgr is not None:
                client_name, is_inherited = client_mgr.resolve_client_name(extracted_client_name)
                if is_inherited:
                    logger.info(f"[{thread_name}] Document has no explicit client. Inheriting active client context: '{client_name}'")
                elif client_name.lower() in ("temporary", "temp"):
                    logger.info(f"[{thread_name}] Document has no explicit client. Defaulting to 'Temporary'")
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
                        "dest_path": dest_path,
                        "dest_filename": os.path.basename(dest_path),
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
                            "client_name": client_name or "Temporary",
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
                        "dest_path": dest_path,
                        "dest_filename": target_name,
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
