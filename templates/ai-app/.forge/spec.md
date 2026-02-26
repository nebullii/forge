# Project: [Your AI App Name]

## What
[An AI-powered application that uses LLMs to do X for Y users]

## Users
- [Primary user type]
- [Secondary user type]

## Features
- [ ] [AI-powered feature 1]
- [ ] [AI-powered feature 2]
- [ ] Client-side caching of previous results in localStorage

## AI Provider
- Provider: OpenAI / Anthropic (pick one)
- Model: gpt-4o / claude-sonnet (pick one)
- Use case: Analysis / Chat / Completion

## Prompts
Describe the main prompts/behaviors:
- System prompt: [What persona/role should the AI have?]
- Key behaviors: [What should it do? What should it avoid?]
- Response length: [Keep it short and punchy, or detailed?]

## Pages
- `/` - Main interface with selector/input and AI-generated results
- `/detail/:id` - Detail view with AI analysis + supporting data
- `/compare` - Side-by-side comparison with AI commentary

## API Endpoints
- `POST /api/analyze` - Send input, get AI-generated analysis
- `POST /api/compare-analyze` - Compare two items with AI commentary
- `GET /api/items/names` - List items for dropdowns (no data exposed upfront)
- [Add your endpoints]

## Vibe
[Snarky and fun? Professional? Conversational? Describe the feel]

## Example: Team Picker
A working example of this template: users pick an NFL team from a dropdown,
OpenAI generates a snarky verdict on whether to root for them based on
Super Bowl history. No stats shown upfront -- the surprise is the point.

## Judging Notes
- Innovation: [What's new/creative about your AI use case?]
- Technical: [Prompt engineering? Caching? Streaming?]
- Impact: [Who benefits and how?]
- Completion: [What % is working?]
