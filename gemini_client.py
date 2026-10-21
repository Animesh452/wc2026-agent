"""Shared Gemini client and retry logic.

Every Gemini call, in the agent loop and inside tools, goes through
generate_with_retry() so 429/500/503 errors are retried with backoff.
Kept separate from agent.py so tools can use it without a circular import.
"""

import asyncio, random
import os

from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT_ID"),
    location="global"
)


MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
RETRYABLE_CODES = {429, 500, 503}


async def generate_with_retry(contents, config, max_attempts=4):
    for attempt in range(1, max_attempts + 1):
        try:
            return await client.aio.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except errors.APIError as e:
            if e.code not in RETRYABLE_CODES or attempt == max_attempts:
                raise
            delay = (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"  Gemini {e.code}, retrying in {delay:.1f}s (attempt {attempt}/{max_attempts})")
            await asyncio.sleep(delay)
