from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()

client = genai.Client(
    vertexai=True,
    project=os.getenv("GCP_PROJECT_ID"),
    location="global"
)

get_score_func = types.FunctionDeclaration(
    name="get_match_score",
    description="Get the current score for a World Cup match",
    parameters={
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "description": "Name of the team"
            }
        },
        "required": ["team"]
    }
)

response = client.models.generate_content(
    model="gemini-3.1-pro-preview",
    contents="What's the current score for Brazil?",
    config=types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[get_score_func])]
    )
)

for part in response.candidates[0].content.parts:
    if part.function_call:
        print(f"Tool called: {part.function_call.name}")
        print(f"Args: {dict(part.function_call.args)}")
    elif part.text:
        print(f"Text: {part.text}")