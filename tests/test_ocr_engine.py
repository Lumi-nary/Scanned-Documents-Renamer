import os
import io
import shutil
import tempfile
import unittest
import fitz
from PIL import Image, ImageDraw

from src.ocr_engine import extract_pdf_pages_text, get_ocr_engine
from src.organizer import classify_pdf_by_rules
from src.client_manager import extract_client_name_from_pdf

class TestOcrEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_digital_text_extraction(self):
        pdf_path = os.path.join(self.test_dir, "digital_sample.pdf")
        doc = fitz.open()
        p = doc.new_page()
        p.insert_textbox(fitz.Rect(50, 50, 500, 300), "Transmittal Sheet\nDate: January 8, 2024\nZenith Realty Development Corp.")
        doc.save(pdf_path)
        doc.close()

        p1_text, full_text = extract_pdf_pages_text(pdf_path)
        self.assertIn("Transmittal Sheet", p1_text)
        self.assertIn("Zenith Realty", p1_text)

        target = classify_pdf_by_rules(pdf_path, text_p1=p1_text, text_full=full_text)
        self.assertEqual(target, "Transmittal Sheet 01_08_2024.pdf")

        client = extract_client_name_from_pdf(pdf_path, text_p1=p1_text, text_full=full_text)
        self.assertEqual(client, "Zenith Realty Development Corp")

    def test_scanned_image_ppocr_extraction(self):
        engine = get_ocr_engine()
        if engine is None:
            self.skipTest("RapidOCR not available")

        # Create a purely scanned image PDF with no digital text
        pdf_path = os.path.join(self.test_dir, "scanned_sample.pdf")
        doc = fitz.open()
        p = doc.new_page(width=600, height=800)

        img = Image.new("RGB", (600, 800), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 60), "SECRETARY CERTIFICATE", fill="black")
        draw.text((50, 110), "Corporate Secretary of Bluestar J3 Corp", fill="black")
        draw.text((50, 160), "Doc. No. 74 Page No. 15 Series of 2025", fill="black")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        p.insert_image(p.rect, stream=buf.getvalue())
        doc.save(pdf_path)
        doc.close()

        # Verify no digital text
        with fitz.open(pdf_path) as check_doc:
            self.assertEqual(len(check_doc[0].get_text().strip()), 0)

        # Run extraction which triggers local PP-OCR
        p1_text, full_text = extract_pdf_pages_text(pdf_path)
        self.assertTrue(len(p1_text) > 0)
        self.assertIn("74", p1_text)

        target = classify_pdf_by_rules(pdf_path, text_p1=p1_text, text_full=full_text)
        self.assertEqual(target, "Secretary's Certificate Doc. No. 74.pdf")

        client = extract_client_name_from_pdf(pdf_path, text_p1=p1_text, text_full=full_text)
        self.assertEqual(client, "Bluestar J3 Corp")

    def test_garbled_ocr_triggers_ppocr_fallback(self):
        engine = get_ocr_engine()
        if engine is None:
            self.skipTest("RapidOCR not available")

        # Create a PDF with both an image containing clean text AND a corrupted digital text layer
        pdf_path = os.path.join(self.test_dir, "garbled_sample.pdf")
        doc = fitz.open()
        p = doc.new_page(width=600, height=800)

        img = Image.new("RGB", (800, 600), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 60), "CERTIFICATE OF MEDICAL EXAMINATION", fill="black")
        draw.text((50, 110), "Client: Edgar Borillo", fill="black")
        draw.text((50, 160), "Date: Aug 29, 2022", fill="black")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        p.insert_image(p.rect, stream=buf.getvalue())

        # Insert corrupted text layer with \ufffd and fragmented lines
        corrupted_text = "\ufffd\n8\nEDGAk L BOULLO\n\ufffd\nfl\n\ufffd\n\ufffd\n\ufffd\n"
        p.insert_textbox(fitz.Rect(50, 50, 400, 200), corrupted_text)
        doc.save(pdf_path)
        doc.close()

        # Execute text extraction - should detect garbled text layer and execute PP-OCR
        p1_text, full_text = extract_pdf_pages_text(pdf_path)
        self.assertIn("MEDICAL", p1_text.upper())

        # Test known clients matching
        known = ["Boxes", "Edgar Borillo", "Finance", "General Clients"]
        client = extract_client_name_from_pdf(pdf_path, text_p1=p1_text, text_full=full_text, known_clients=known)
        self.assertEqual(client, "Edgar Borillo")

        # Test classification
        target = classify_pdf_by_rules(pdf_path, text_p1=p1_text, text_full=full_text)
        self.assertEqual(target, "Certificate of Medical Examination 08_29_2022.pdf")

if __name__ == "__main__":
    unittest.main()
