# test_claude.py
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

message = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=100,
    messages=[{"role": "user", "content": "Say hello in one sentence"}]
)

print("Claude says:", message.content[0].text)