# Build Rules

## Stack
- Framework: FastAPI (Python 3.10+)
- Database: SQLite
- Validation: Pydantic

## Structure
```
/
├── main.py            # FastAPI app entry
├── routes/            # API route handlers
├── models/            # Pydantic models
├── db.py              # Database setup
├── requirements.txt
└── README.md
```

## Constraints
- REST conventions (proper HTTP methods, status codes)
- JSON responses only
- SQLite for persistence
- No external services

## API Rules
- Use proper HTTP status codes
- Return consistent response format
- Include pagination for list endpoints
- Validate all input with Pydantic

## Response Format
```json
{
  "data": {...},
  "error": null
}
```

## Error Format
```json
{
  "data": null,
  "error": {
    "code": "NOT_FOUND",
    "message": "Item not found"
  }
}
```

## Deploy Target
- Railway, Render, or Cloud Run
- Single container deployment
