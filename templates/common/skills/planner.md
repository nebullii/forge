# Planner Skills

## Task Sizing
- Produce 3–8 tasks per build; more tasks = slower builds with no quality gain
- Each task should touch at most 4 files; if more are needed, split the task
- Tasks must be independently executable by the coder — no "do X then Y in the same task"

## Task Ordering
Follow this sequence unless the spec requires otherwise:
1. Project setup (structure, config files, requirements)
2. Data models / database schema
3. Backend routes and services
4. Frontend components and pages
5. Integration (wiring API → UI, env vars, Vite proxy)

## Technology Defaults
- Follow rules.md stack choices exactly — do not introduce alternatives
- Prefer sqlite3 over any ORM
- Prefer plain JavaScript/JSX over TypeScript unless spec says otherwise
- Use FastAPI for any Python API

## Output Format
Return a JSON object with:
- `decisions`: stack choices and reasoning
- `tasks`: array of `{id, name, description, agent}` objects

## Pitfalls to Avoid
- Do NOT create a standalone "write documentation" task
- Do NOT add a testing task unless the spec explicitly requests tests
- Do NOT create tasks that only create empty placeholder files
- Task descriptions must be specific enough for the coder to act on without asking questions
