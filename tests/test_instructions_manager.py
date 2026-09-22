import os
import json
import tempfile
import unittest
from src.instructions_manager import InstructionsManager, PRESET_FILE_TYPES

class TestInstructionsManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.instructions_file = os.path.join(self.temp_dir.name, "test_instructions.json")
        self.mgr = InstructionsManager(instructions_file=self.instructions_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_initialization(self):
        # File should have been saved
        self.assertTrue(os.path.exists(self.instructions_file))
        self.assertEqual(len(self.mgr.file_types), len(PRESET_FILE_TYPES))
        prompt = self.mgr.get_system_prompt()
        self.assertIn("CATEGORIZATION RULES:", prompt)
        self.assertIn("Statement of Account", prompt)
        self.assertIn("Corporate Officer & Secretary Pattern", prompt)
        self.assertIn("EXAMPLE RESPONSES:", prompt)

    def test_add_and_update_custom_rule(self):
        custom_rule = {
            "id": "court_pleadings",
            "name": "Court Pleadings & Motions",
            "is_preset": False,
            "enabled": True,
            "priority": 1,
            "match_keywords": ["Motion for Reconsideration", "Entry of Appearance", "Pleading"],
            "naming_format": "Pleading <Case_No> MM_DD_YYYY.pdf",
            "instructions": "Extract court branch and case docket number."
        }
        current_types = list(self.mgr.file_types)
        current_types.insert(0, custom_rule)
        
        self.mgr.update_instructions({
            "file_types": current_types
        })

        # Reload from disk to verify persistence
        new_mgr = InstructionsManager(instructions_file=self.instructions_file)
        self.assertEqual(len(new_mgr.file_types), len(PRESET_FILE_TYPES) + 1)
        self.assertEqual(new_mgr.file_types[0]["id"], "court_pleadings")
        
        prompt = new_mgr.get_system_prompt()
        self.assertIn("Court Pleadings & Motions", prompt)
        self.assertIn("Motion for Reconsideration", prompt)

    def test_native_match_custom_rule(self):
        custom_rule = {
            "id": "tax_clearance",
            "name": "Tax Clearance Certificate",
            "is_preset": False,
            "enabled": True,
            "priority": 1,
            "match_keywords": ["Tax Clearance", "Certificate of Tax Clearance"],
            "naming_format": "Tax Clearance Certificate.pdf",
            "instructions": "Standard tax clearance certificate."
        }
        self.mgr.update_instructions({
            "file_types": [custom_rule] + list(self.mgr.file_types)
        })

        matched = self.mgr.match_custom_rule_native(
            text_p1="This is to certify that Tax Clearance has been issued.",
            text_full="",
            file_basename="scan101.pdf"
        )
        self.assertEqual(matched, "Tax Clearance Certificate.pdf")

    def test_reset_to_defaults(self):
        # Modify rules
        self.mgr.update_instructions({
            "file_types": [{
                "id": "temp_rule",
                "name": "Temporary Document",
                "is_preset": False,
                "enabled": True,
                "priority": 1,
                "match_keywords": ["temp"],
                "naming_format": "Temp.pdf",
                "instructions": "Temp instructions."
            }]
        })
        self.assertEqual(len(self.mgr.file_types), 1)

        # Reset
        self.mgr.reset_to_defaults()
        self.assertEqual(len(self.mgr.file_types), len(PRESET_FILE_TYPES))
        self.assertTrue(any(r["id"] == "statement_of_account" for r in self.mgr.file_types))

if __name__ == "__main__":
    unittest.main()
