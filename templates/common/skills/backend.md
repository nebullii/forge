# Backend Skills

## Route Handler Patterns
- Keep route handlers thin: validate input, call a service function, return the result
- Put business logic in a `services/` module, not inside route handlers
- `GET /` must return a health-check JSON: `{"status": "ok", "version": "0.1.0"}`

## CORS
- Always add CORS middleware when a frontend is present
- Allow origins from `VITE_API_URL` or use `["*"]` for local dev with a comment explaining why

## Secrets Management
- All secrets must come from `os.environ.get("VAR_NAME")` — never hardcode
- Add a `.env.example` file listing every required environment variable with a placeholder value

## Database
- Use sqlite3 directly — no ORMs
- Always use parameterized queries
- Create tables in an `init_db()` function called at startup
- Store the DB path in an environment variable `DATABASE_URL`, defaulting to `./data.db`

## Error Handling
- Return proper HTTP status codes: 404 for not found, 422 for validation errors, 500 for server errors
- Wrap database calls in try/except and return a 500 with a safe error message (no stack traces)

## What NOT to Do
- No Celery, no message queues, no background tasks unless spec requires them
- No GraphQL — use REST
- No complex auth systems — use simple JWT or session-based auth if needed
