import os
import shutil
import tempfile
import unittest

from src.batch import BatchManifestBuilder

class TestBatch(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_batch_manifest_builder(self):
        builder = BatchManifestBuilder(model_name="deepseek-chat")
        
        sample_file = os.path.join(self.test_dir, "batch_sample.txt")
        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("Batch payload document text.")

        success = builder.add_file(sample_file)
        self.assertTrue(success)
        self.assertEqual(len(builder.records), 1)

        out_jsonl = os.path.join(self.test_dir, "batch_output.jsonl")
        exported = builder.export_jsonl(out_jsonl)
        
        self.assertTrue(os.path.exists(exported))
        with open(exported, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("batch_sample.txt", lines[0])

if __name__ == "__main__":
    unittest.main()
