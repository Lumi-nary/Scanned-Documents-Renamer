import os
import shutil
import tempfile
import unittest
from src.organizer import parse_date_from_text, classify_pdf_by_rules
from src.worker import sanitize_filename

class TestOrganizer(unittest.TestCase):
    def test_parse_date_from_text(self):
        text1 = "Date: January 4, 2023"
        self.assertEqual(parse_date_from_text(text1), "01_04_2023")

        text2 = "Mandaluyong City, December 29, 2022"
        self.assertEqual(parse_date_from_text(text2), "12_29_2022")

    def test_sanitize_filename_ope(self):
        self.assertEqual(sanitize_filename("OPE-1185.pdf"), "1185.pdf")
        self.assertEqual(sanitize_filename("Statement of Account - Out-of-Pocket Expenses OPE-1185.pdf"), "1185.pdf")
        self.assertEqual(sanitize_filename("Statement of Account - Out-of-Pocket Expenses OPE 1185.pdf"), "1185.pdf")
        self.assertEqual(sanitize_filename("Statement of Account - Out-of-Pocket Expenses 09_10_2024.pdf"), "09102024.pdf")
        self.assertEqual(sanitize_filename("Statement of Account No. 2022-0129.pdf"), "20220129.pdf")
        self.assertEqual(sanitize_filename("Summary of Services Litigation - May to August 2018.pdf"), "Summary of Services May to August 2018.pdf")
        self.assertEqual(sanitize_filename("SOA20240551.pdf"), "20240551.pdf")
        self.assertEqual(sanitize_filename("SOA-20240551.pdf"), "20240551.pdf")

    def test_sanitize_filename_liquidation(self):
        self.assertEqual(
            sanitize_filename("Liquidation of Deposit for Out-of-Pocket Expenses 12092020.pdf"),
            "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf"
        )
        self.assertEqual(
            sanitize_filename("Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf"),
            "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf"
        )
        self.assertEqual(
            sanitize_filename("Re Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf"),
            "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf"
        )

    def test_classify_pdf_by_rules_liquidation_of_deposit(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_liquidation_deposit.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "METRO LEGAL & ASSOCIATES LAW OFFICES\nDecember 9, 2020\nRe: Liquidation of Deposit for Out-of-Pocket Expenses\nWe enclose an Accounting of Deposit for Expenses...")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_soa_hyphenated(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_soa_2022_0129.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "METRO LEGAL & ASSOCIATES LAW OFFICES\nSTATEMENT OF ACCOUNT\nNo. 2022-0129\nDate: February 24, 2022")
        page2 = doc.new_page()
        page2.insert_text((50, 50), "Summary of Services Rendered for Sunnyvale Community Association\nLitigation - October to December 2021")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "20220129.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_summary_of_services(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_summary_services.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "METRO LEGAL & ASSOCIATES LAW OFFICES\nSummary of Services Rendered for Sunnyvale Community Association\nLitigation - February to June 2019\nFILE IN CLIENT'S ACCOUNTING FILE 8-11-19")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Summary of Services February to June 2019.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_soa_5digit(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_soa_13656.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "Harrison & Partners Law Offices\nSTATEMENT OF ACCOUNT\nDecember 5, 2014\nNo 13656")
        page2 = doc.new_page()
        page2.insert_text((50, 50), "HARRISON & PARTNERS LAW OFFICES\nSummary of Services Rendered for Sunnyvale Community\nLitigation - August 2014")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "13656.pdf")
        finally:
            if os.path.exists(temp_pdf):

                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_secretarys_certificate(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_secretarys_certificate.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "REPUBLIC OF THE PHILIPPINES\nSECRETARY'S CERTIFICATE\nJune 26, 2025\nI, the undersigned Corporate Secretary...")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Secretary's Certificate 06_26_2025.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_secretarys_certificate_with_doc_no(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_secretarys_certificate_doc_no.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "REPUBLIC OF THE PHILIPPINES\nSECRETARY'S CERTIFICATE\n09 September 2025\nI, JUAN DELA CRUZ...\nDoc. No.: 387;\nPage No.: 78;\nBook No.: II;\nSeries of 2025.")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Secretary's Certificate Doc. No. 387.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_secretarys_certificate_multipage_doc_no_on_last_page(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_secretarys_cert_p2_doc_no.pdf")
        doc = fitz.open()
        # Page 1 has title and resolutions only, ends with (signature page follows)
        page1 = doc.new_page()
        page1.insert_text((50, 50), "REPUBLIC OF THE PHILIPPINES\nSECRETARY'S CERTIFICATE\nI, JUAN DELA CRUZ...\n(signature page follows)")
        # Page 2 has the notary section with Doc. No.
        page2 = doc.new_page()
        page2.insert_text((50, 50), "IN WITNESS WHEREOF...\nSUBSCRIBED AND SWORN to before me this 10 SEP 2025\nDoc. No.: 388;\nPage No.: 78;\nBook No.: II;\nSeries of 2025.")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Secretary's Certificate Doc. No. 388.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_certificate_of_incorporation_id(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_cert_incorporation.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "Securities and Exchange Commission\nCERTIFICATE OF INCORPORATION\nCompany Reg. No. 2025060206219-60\nThis is to certify that...")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Certificate of Incorporation 2025060206219-60.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_certificate_of_incorporation_multipage_no_date_fallback(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_cert_incorp_multipage.pdf")
        doc = fitz.open()
        # Page 1 has Company Reg No. and words date
        page1 = doc.new_page()
        page1.insert_text((50, 50), "REPUBLIC OF THE PHILIPPINES\nSECURITIES AND EXCHANGE COMMISSION\nCOMPANY REG. NO.: 2025030195697-02\nCERTIFICATE OF INCORPORATION\nVERTEX CONSULTANCY, OPC")
        # Page 2 has eOR receipt with a date
        page2 = doc.new_page()
        page2.insert_text((50, 50), "electronic Official Receipt\nMarch 28, 2025\nPayment Assessment Details\nPAF Date 2025-03-28")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Certificate of Incorporation 2025030195697-02.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_certificate_of_registration_ocn(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_cert_registration.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "BIR FORM 2303\nCERTIFICATE OF REGISTRATION\nOCN: 041RC20250000005534\nDate OCN Generated: October 21, 2025\nTIN: 687-730-668-00000\nATLAS PHARMACEUTICALS, INC.")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Certificate of Registration 041RC20250000005534.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_application_for_registration_tin(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_app_registration.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "BIR Form No. 1903\nApplication for Registration\n682-974-124-00000\nEffectivity Date 01 01 2025\nDate of Incorporation 10 17 2025\nATLAS PHARMACEUTICALS, INC.")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Application for Registration 682-974-124-00000.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_authority_to_print_ocn(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_atp.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "BIR Form 1906\nAUTHORITY TO PRINT\nOCN: 041RC20250000005534\nATLAS PHARMACEUTICALS, INC.")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Authority to Print 041RC20250000005534.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_documentary_stamp_tax(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_dst.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "BIR Form No. 2000-OT\nMonthly Documentary Stamp Tax Declaration/Return\nFor the Month of: 08/2025\nATLAS PHARMACEUTICALS, INC.")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Monthly Documentary Stamp Tax Declaration Return 08_2025.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_sanitize_filename_declaration_return_slash(self):
        self.assertEqual(
            sanitize_filename("Monthly Documentary Stamp Tax Declaration/Return 08_2025.pdf"),
            "Monthly Documentary Stamp Tax Declaration Return 08_2025.pdf"
        )
        self.assertEqual(
            sanitize_filename("Monthly Documentary Stamp Tax DeclarationReturn 08_2025.pdf"),
            "Monthly Documentary Stamp Tax Declaration Return 08_2025.pdf"
        )

    def test_sanitize_filename_secretarys_certificate_doc_no(self):
        self.assertEqual(
            sanitize_filename("Secretary's Certificate Doc. No.: 387.pdf"),
            "Secretary's Certificate Doc. No. 387.pdf"
        )
        self.assertEqual(
            sanitize_filename("Secretary's Certificate Doc No 387.pdf"),
            "Secretary's Certificate Doc. No. 387.pdf"
        )

    def test_pdf_to_base64_images_multipage(self):
        from src.worker import pdf_to_base64_images
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_render_multipage.pdf")
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((50, 50), "Page 1 Content")
        p2 = doc.new_page()
        p2.insert_text((50, 50), "Page 2 Content")
        doc.save(temp_pdf)
        doc.close()

        try:
            images = pdf_to_base64_images(temp_pdf)
            self.assertEqual(len(images), 2)
            self.assertTrue(images[0].startswith("data:image/png;base64,"))
            self.assertTrue(images[1].startswith("data:image/png;base64,"))
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def test_classify_pdf_by_rules_unrecognized_fallback(self):
        import fitz
        temp_pdf = os.path.join(tempfile.gettempdir(), "test_unrecognized.pdf")
        doc = fitz.open()
        page1 = doc.new_page()
        page1.insert_text((50, 50), "BARANGAY CENTRAL DISTRICT 1\nNAME AGE BDAY GENDER ADDRESS CONTACT NO. SIGNATURE\nRandom table without title...")
        doc.save(temp_pdf)
        doc.close()

        try:
            result_filename = classify_pdf_by_rules(temp_pdf)
            self.assertEqual(result_filename, "Unrecognized.pdf")
        finally:
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)


    def test_resolve_filename_collision(self):
        from src.organizer import resolve_filename_collision
        temp_dir = tempfile.mkdtemp()
        filename = "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020.pdf"
        file1 = os.path.join(temp_dir, filename)

        try:
            # 1. No collision
            fn1, path1 = resolve_filename_collision(temp_dir, filename)
            self.assertEqual(fn1, filename)
            with open(path1, "w") as f:
                f.write("file 1")

            # 2. Collision 1 -> should append _2
            fn2, path2 = resolve_filename_collision(temp_dir, filename)
            self.assertEqual(fn2, "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020_2.pdf")
            with open(path2, "w") as f:
                f.write("file 2")

            # 3. Collision 2 -> should append _3
            fn3, path3 = resolve_filename_collision(temp_dir, filename)
            self.assertEqual(fn3, "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020_3.pdf")
            with open(path3, "w") as f:
                f.write("file 3")

            # 4. Collision 3 -> should append _4
            fn4, path4 = resolve_filename_collision(temp_dir, filename)
            self.assertEqual(fn4, "Liquidation of Deposit for Out-of-Pocket Expenses 12_09_2020_4.pdf")

            # 5. Collision with Doc. No.
            doc_no_fn = "Secretary's Certificate Doc. No. 387.pdf"
            dn1, dn_path1 = resolve_filename_collision(temp_dir, doc_no_fn)
            self.assertEqual(dn1, doc_no_fn)
            with open(dn_path1, "w") as f:
                f.write("doc no file 1")

            dn2, dn_path2 = resolve_filename_collision(temp_dir, doc_no_fn)
            self.assertEqual(dn2, "Secretary's Certificate Doc. No. 387_2.pdf")
            with open(dn_path2, "w") as f:
                f.write("doc no file 2")

            dn3, dn_path3 = resolve_filename_collision(temp_dir, doc_no_fn)
            self.assertEqual(dn3, "Secretary's Certificate Doc. No. 387_3.pdf")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
