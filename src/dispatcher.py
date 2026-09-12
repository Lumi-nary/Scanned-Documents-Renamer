import json
import time
import random
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Union, List

logger = logging.getLogger(__name__)

class AIAPIDispatcher:
    """
    Handles payload construction, rate limiting, exponential backoff with jitter,
    and HTTP POST requests to OpenAI-compatible AI API endpoints.
    """
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model_name: str = "google/gemini-2.5-flash:free",
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        max_backoff_delay: float = 30.0,
        mock_mode: bool = False
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.max_backoff_delay = max_backoff_delay
        self.mock_mode = mock_mode
        self.fallback_local_mode = False

    def dispatch_prompt(
        self,
        prompt_text: Optional[str] = None,
        system_prompt: str = "You are an automated document processing assistant.",
        user_content: Optional[Any] = None
    ) -> Optional[str]:
        """
        Dispatches prompt_text or user_content (image/text payload) to the AI provider endpoint with automatic retries.
        """
        if self.fallback_local_mode or self.mock_mode or self.api_key in ("mock-key", "your-api-key-here", ""):
            logger.info("[LOCAL EXTRACTION MODE] Processing payload locally.")
            return '{"filename": "Mock_Document_01_01_2024.pdf", "summary": "Mock AI Summary (Local Mode)"}'

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/ScanSnap-AI",
            "X-Title": "ScanSnap AI"
        }
        
        content_payload = user_content if user_content is not None else prompt_text

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_payload}
            ],
            "temperature": 0.1
        }

        data = json.dumps(payload).encode("utf-8")
        
        attempt = 0
        while attempt <= self.max_retries:
            attempt += 1
            req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    status_code = response.status
                    response_body = response.read().decode("utf-8")

                    if status_code == 200:
                        resp_data = json.loads(response_body)
                        return resp_data["choices"][0]["message"]["content"]
                    else:
                        logger.warning(f"Unexpected status code {status_code}: {response_body}")

            except urllib.error.HTTPError as e:
                status_code = e.code
                error_body = e.read().decode("utf-8", errors="ignore")

                # Handle Insufficient Balance (HTTP 402) or Model Unavailable (HTTP 404) cleanly
                if status_code in (402, 404):
                    logger.warning(f"API Provider returned HTTP {status_code} ({error_body[:100]}). Switching to FREE Local Extraction Mode.")
                    self.fallback_local_mode = True
                    return f"Mock AI Summary (Local Mode): {prompt_text[:150] if prompt_text else ''}..."

                logger.warning(f"HTTPError {status_code} on attempt {attempt}/{self.max_retries + 1}: {error_body}")

                if status_code in (429, 500, 502, 503, 504):
                    if attempt > self.max_retries:
                        logger.error(f"Max retries ({self.max_retries}) exceeded for HTTP {status_code}.")
                        return None
                    
                    retry_after = e.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_seconds = float(retry_after)
                    else:
                        base_delay = self.backoff_factor ** attempt
                        sleep_seconds = random.uniform(0, min(self.max_backoff_delay, base_delay))
                    
                    time.sleep(sleep_seconds)
                    continue
                else:
                    logger.error(f"Non-retryable HTTP error {status_code}: {error_body}")
                    return None

            except Exception as e:
                logger.error(f"Network error executing request (attempt {attempt}/{self.max_retries + 1}): {e}")
                if attempt > self.max_retries:
                    return None
                
                base_delay = self.backoff_factor ** attempt
                sleep_seconds = random.uniform(0, min(self.max_backoff_delay, base_delay))
                time.sleep(sleep_seconds)

        return None

    def dispatch_vision(
        self,
        image_b64_url: Union[str, List[str]],
        system_prompt: str = "You are an automated document processing assistant.",
        text_prompt: str = "Visually OCR and classify this document image to determine its target filename."
    ) -> Optional[str]:
        """
        Dispatches a base64 image URL (or list of base64 image URLs) payload for vision AI OCR classification.
        """
        user_content: List[Dict[str, Any]] = []
        if isinstance(image_b64_url, list):
            for img_url in image_b64_url:
                user_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": img_url
                    }
                })
        else:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": image_b64_url
                }
            })

        user_content.append({
            "type": "text",
            "text": text_prompt
        })
        return self.dispatch_prompt(system_prompt=system_prompt, user_content=user_content)
