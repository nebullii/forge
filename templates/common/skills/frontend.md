# Frontend Skills

## File Structure
- One component per file — no multi-component files
- Pages go in `src/pages/`, reusable components in `src/components/`
- All API calls go in a single `src/api.js` (or `src/api/index.js`) file

## API Integration
- Read the base URL from `import.meta.env.VITE_API_URL` — never hardcode `localhost`
- Add a Vite proxy config in `vite.config.js`: `/api` → backend URL during development
- Export one function per API endpoint from `api.js`

## Component State
Every component that fetches data must handle exactly these three states:
1. **Loading** — show a spinner or "Loading..." text
2. **Error** — show an error message with the error text
3. **Data** — render the actual content

## Styling
- Use Tailwind CSS utility classes unless the spec says otherwise
- Keep inline styles minimal — use Tailwind classes for layout and spacing
- Mobile-first: use `sm:`, `md:` prefixes for breakpoints

## Environment Files
- Create `.env.example` with `VITE_API_URL=http://localhost:8000`
- Create `.env` with the same defaults for local dev

## What NOT to Do
- No TypeScript unless spec requires it
- No Redux, Zustand, or React Query — use useState + useEffect + fetch()
- No class components — use function components only
- No direct DOM manipulation — let React manage the DOM
