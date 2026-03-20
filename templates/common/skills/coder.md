# Coder Skills

## Completeness Rules
- Every file must be complete and runnable as delivered — no placeholders, no TODOs, no `...`
- Always include all import statements at the top of each file
- Never emit partial functions or classes; write the whole thing
- If a file is long, still write the whole thing — do not truncate

## SQL Safety
- Always use parameterized queries: `cursor.execute("SELECT * FROM t WHERE id = ?", (id,))`
- Never use f-strings or string concatenation to build SQL queries
- Always call `conn.commit()` after INSERT/UPDATE/DELETE

## React Patterns
- Every data-fetching component must handle three states: loading, error, and data
- Use `VITE_API_URL` (from `.env`) as the base URL for all fetch calls — never hardcode localhost
- Export each component as a named export and as the default export

## File Output Format
Output each file using this exact format:
```file:path/to/file.ext
<file contents>
```

## What NOT to Do
- Do not add features not mentioned in the task or spec
- Do not write tests unless the spec asks for them
- Do not create README.md files
- Do not add logging frameworks — use print() or console.log() only
