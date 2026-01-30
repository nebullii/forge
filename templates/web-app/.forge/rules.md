# Build Rules

## Stack
- Frontend: React 18+ with Vite
- Backend: FastAPI with Python 3.10+
- Database: SQLite (single file, no setup)
- Styling: Tailwind CSS

## Structure
```
/
├── frontend/          # React app
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
├── backend/           # FastAPI app
│   ├── main.py
│   ├── routes/
│   └── requirements.txt
└── README.md
```

## Constraints
- Free tiers only (no paid services)
- Single repo, single deploy
- SQLite for data (no external DB)
- Environment variables for all secrets

## Frontend Rules
- Functional components only
- Use fetch() for API calls
- Responsive design (mobile-first)
- No unnecessary dependencies

## Backend Rules
- FastAPI with automatic OpenAPI docs
- Pydantic for validation
- SQLite with raw SQL or sqlite3
- CORS enabled for frontend

## Deploy Target
- Vercel (frontend) or combined
- Or Railway/Render for full-stack
