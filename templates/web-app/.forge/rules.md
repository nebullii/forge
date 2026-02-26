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
- Free tiers only — no paid services
- Single repo, single deploy to Railway
- SQLite with sqlite3 (stdlib) — no ORM, no external DB
- Environment variables for all secrets

## What NOT to use
- SQLAlchemy or any ORM — raw sqlite3 only
- TypeScript — plain JavaScript/JSX
- Redux, Zustand, React Query — useState/useEffect + fetch()
- Celery or task queues
- GraphQL

## Use when appropriate
- Redis — for caching frequently read data or session storage
- Docker + docker-compose — when stack includes Redis or multiple services

## Frontend Rules
- Functional components, plain JSX
- fetch() for all API calls — no Axios
- Tailwind for all styling — no component libraries
- Responsive, mobile-first

## Backend Rules
- FastAPI + Pydantic for validation
- sqlite3 for database — raw SQL
- CORS middleware enabled
- Proper HTTP status codes and error responses

## Deploy Target
- Railway (full-stack, single service)
