# Build Rules

## Stack
- Frontend: React 18+ with Vite
- Backend: FastAPI (Python 3.10+)
- Database: SQLite (for source data)
- AI SDK: openai / anthropic (Python)
- Styling: Tailwind CSS

## Structure
```
/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── Layout.jsx
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   ├── Detail.jsx
│   │   │   └── Compare.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── main.py
│   └── requirements.txt
├── .env
└── README.md
```

## Constraints
- Never commit API keys (use .env + python-dotenv)
- Handle API errors gracefully (show user-friendly messages)
- Keep LLM prompts short and specific -- no essay responses
- Cache results client-side in localStorage where appropriate

## API Key Handling
```python
# Load from environment
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")  # or ANTHROPIC_API_KEY

# Never log or return API keys
# Never include in frontend code
```

## AI Best Practices
- Keep prompts concise: ask for 3-5 sentences, not paragraphs
- Set reasonable max_tokens (512-1024 for analysis)
- Build prompts from real data (DB stats, history) for grounded responses
- Parse structured output from LLM (e.g., scores on first line)
- Handle API errors without breaking the UI

## Frontend Rules
- Show loading state during LLM calls ("Generating analysis...")
- Don't expose raw data upfront -- let the AI reveal it (element of surprise)
- Cache previous results in localStorage for instant replay
- Show cached results as small cards below the main content
- Handle loading and error states gracefully

## Backend Rules
- Separate data-fetching (DB queries) from LLM calls
- Build prompts by assembling context from the database
- Return structured JSON: { analysis, score, metadata }
- Keep existing CRUD endpoints for supporting data
- Add lightweight endpoints for dropdowns (names only, no stats)

## Frontend Caching Pattern
```javascript
const CACHE_KEY = 'app-history'
function loadCache() {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || '[]') }
  catch { return [] }
}
function saveToCache(entry) {
  const history = loadCache().filter(h => h.id !== entry.id)
  history.unshift(entry)
  localStorage.setItem(CACHE_KEY, JSON.stringify(history.slice(0, 20)))
}
```

## Deploy Target
- Railway/Render (full-stack)
- Set API keys as environment secrets
