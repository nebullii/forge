# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this API step by step. Start with models, then routes, then main.py."
```

## Add an endpoint
```bash
claude "Read .forge/spec.md. Add a new endpoint: [describe endpoint] following the rules in .forge/rules.md."
```

## Fix an issue
```bash
claude "Read .forge/spec.md. The API returns this error: [describe error]. Fix it."
```

## Add authentication
```bash
claude "Read .forge/spec.md and rules.md. Add API key authentication to all endpoints."
```

## Add tests
```bash
claude "Read the codebase. Add pytest tests for all endpoints."
```

## Generate sample data
```bash
claude "Read .forge/spec.md. Create a script to seed the database with sample data for testing."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this API following rules.md"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this API step by step
```

---

## Tips

- **Test as you go**: Use `/docs` endpoint to test in browser
- **Check status codes**: Make sure errors return proper HTTP codes
- **Validate input**: Use Pydantic models for all requests
