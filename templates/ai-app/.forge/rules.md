# Build Rules

## Stack
- Frontend: React 18+ with Vite
- Backend: FastAPI (Python 3.10+)
- Database: SQLite (for conversation history)
- AI SDK: openai / anthropic / together (Python)
- Styling: Tailwind CSS

## Structure
```
/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWindow.jsx
│   │   │   ├── MessageBubble.jsx
│   │   │   └── InputBar.jsx
│   │   ├── pages/
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── main.py
│   ├── routes/
│   │   └── chat.py
│   ├── prompts/
│   │   └── system.txt
│   └── requirements.txt
└── README.md
```

## Constraints
- Free tier APIs (OpenAI has limits, use cheap models)
- Never commit API keys (use .env)
- Handle rate limits gracefully
- Keep prompts in separate files for easy editing

## API Key Handling
```python
# Load from environment
import os
api_key = os.getenv("OPENAI_API_KEY")  # or ANTHROPIC_API_KEY

# Never log or return API keys
# Never include in frontend code
```

## AI Best Practices
- Use streaming for long responses
- Set reasonable max_tokens (500-1000 for chat)
- Include token counting for cost awareness
- Cache responses where appropriate
- Handle API errors (rate limits, timeouts)

## Prompt Engineering
- Keep system prompts in `/backend/prompts/`
- Use clear, specific instructions
- Include examples if needed (few-shot)
- Test prompts manually before coding

## Frontend Rules
- Show typing indicator during AI response
- Stream responses token-by-token if possible
- Persist conversation in localStorage or DB
- Handle loading and error states

## Backend Rules
- Validate input length before sending to API
- Log token usage for cost tracking
- Implement basic rate limiting per user
- Return structured error messages

## Cost Control
- Default to cheapest model (gpt-4o-mini, claude-3-haiku)
- Set max_tokens limits
- Add daily usage caps if needed
- Show users their token usage

## Deploy Target
- Railway/Render (full-stack)
- Set API keys as environment secrets
