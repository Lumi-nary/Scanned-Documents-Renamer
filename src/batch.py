import os
import json
import time
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class BatchManifestBuilder:
    """
    Aggregates file payloads into OpenAI-compatible .jsonl batch request manifests
    for 50% cost savings using provider Batch APIs.
    """
    def __init__(self, model_name: str = "deepseek-chat", system_prompt: str = "You are an automated document processing assistant."):
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.records: List[Dict[str, Any]] = []

    def add_file(self, file_path: str, custom_id: str = None) -> bool:
        """
        Reads target file content and appends a batch request item.
        """
        if not os.path.exists(file_path):
            logger.warning(f"Batch payload target does not exist: {file_path}")
            return False

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            if not content.strip():
                return False

            req_id = custom_id or f"req-{len(self.records) + 1}-{os.path.basename(file_path)}"
            
            record = {
                "custom_id": req_id,
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": content[:4000]}
                    ],
                    "temperature": 0.2
                }
            }
            self.records.append(record)
            return True
        except Exception as e:
            logger.error(f"Error adding file {file_path} to batch manifest: {e}")
            return False

    def export_jsonl(self, output_path: str) -> str:
        """
        Exports collected batch request records to a JSONL file.
        """
        abs_output = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(abs_output), exist_ok=True)
        
        with open(abs_output, 'w', encoding='utf-8') as f:
            for record in self.records:
                f.write(json.dumps(record) + '\n')
                
        logger.info(f"Exported {len(self.records)} batch requests to: {abs_output}")
        return abs_output
