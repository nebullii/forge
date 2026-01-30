# Forge

AI-agnostic project builder. Describe what you want, any AI builds and deploys it.

```
You: "Build a URL shortener with click analytics"
Forge: Here's your live app → https://your-app.run.app
```

## How It Works

```
spec.md (your idea) → Any AI → Complete codebase → Deployed app
```

1. You write what you want in plain English
2. Forge sends it to any AI (Claude, GPT, Gemini, Ollama, etc.)
3. AI designs architecture, writes code, runs tests
4. Forge deploys to free hosting (Cloud Run, Vercel, Railway)

## Quick Start

```bash
# Install
pip install forge-ai

# Create new project
forge new my-app
cd my-app

# Edit spec.md with your idea
vim .forge/spec.md

# Build it (uses your configured AI)
forge build

# Deploy it (free tier)
forge deploy
```

## Configuration

Set your AI provider in `~/.forge/config.yaml`:

```yaml
# Pick one (or multiple for fallback)
providers:
  - name: anthropic
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-20250514

  - name: openai
    api_key: ${OPENAI_API_KEY}
    model: gpt-4o

  - name: ollama
    base_url: http://localhost:11434
    model: llama3

# Deployment (free tiers)
deploy:
  default: gcloud
  gcloud:
    project: ${GCLOUD_PROJECT}
  vercel:
    token: ${VERCEL_TOKEN}
```

## The .forge/ Structure

```
.forge/
├── spec.md        # Your project description (you write this)
├── rules.md       # Constraints (free tier, simple, etc.)
├── decisions.md   # AI writes: tech choices + reasoning
├── tasks.md       # AI writes: task breakdown
└── context/       # AI writes: learnings as it builds
```

## Example spec.md

```markdown
# Project: LinkShort

## What
A URL shortener with click analytics.

## Users
- Anyone who wants to share short links
- Marketers tracking campaign clicks

## Features
- Shorten any URL to a 6-character code
- Track clicks with timestamp, country, device
- Simple dashboard showing click stats
- No login required (anonymous usage)

## Vibe
Minimal, fast, no bloat. Think linktree but simpler.
```

That's it. Forge figures out the rest.

## Commands

| Command | Description |
|---------|-------------|
| `forge new <name>` | Create new project with .forge/ |
| `forge build` | AI builds the entire project |
| `forge build --step` | Build one task at a time (interactive) |
| `forge deploy` | Deploy to configured hosting |
| `forge status` | Show build progress |
| `forge reset` | Start over (keeps spec.md) |

## How AI Builds Your Project

1. **Analyze** - Reads spec.md, understands requirements
2. **Decide** - Picks tech stack, writes to decisions.md
3. **Plan** - Breaks into tasks, writes to tasks.md
4. **Execute** - Builds each task, writes code
5. **Test** - Runs the app, fixes issues
6. **Deploy** - Ships to free hosting

## Supported AI Providers

| Provider | Models | Free Tier |
|----------|--------|-----------|
| Anthropic | Claude 3.5/4 | API credits |
| OpenAI | GPT-4o | API credits |
| Google | Gemini Pro | Free tier |
| Ollama | Llama, Mistral | Local (free) |
| Groq | Llama, Mixtral | Free tier |

## Supported Deployment

| Platform | Free Tier |
|----------|-----------|
| Google Cloud Run | 2M requests/month |
| Vercel | 100GB bandwidth |
| Railway | $5 credit/month |
| Fly.io | 3 shared VMs |
| Render | 750 hours/month |

## Philosophy

- **No templates** - AI designs from scratch
- **No lock-in** - Works with any AI provider
- **No complexity** - Free tiers, single deployable unit
- **No magic** - Everything AI does is visible in .forge/

## License

MIT
