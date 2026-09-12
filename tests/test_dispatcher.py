import unittest
from src.dispatcher import AIAPIDispatcher

class TestDispatcher(unittest.TestCase):
    def test_mock_dispatcher(self):
        dispatcher = AIAPIDispatcher(
            api_key="mock-key",
            base_url="https://api.deepseek.com/v1",
            model_name="deepseek-chat",
            mock_mode=True
        )

        response = dispatcher.dispatch_prompt("Test document content for AI processing.")
        self.assertIsNotNone(response)
        self.assertIn("Mock AI Summary", response)

    def test_default_key_triggers_mock(self):
        dispatcher = AIAPIDispatcher(
            api_key="your-api-key-here",
            base_url="https://api.deepseek.com/v1",
            model_name="deepseek-chat"
        )
        response = dispatcher.dispatch_prompt("Hello world test payload")
        self.assertIsNotNone(response)
        self.assertIn("Mock AI Summary", response)

if __name__ == "__main__":
    unittest.main()
