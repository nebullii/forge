# Forge

Give your AI the structure it needs to build your project.

## The Problem

You open Claude Code / Cursor / Copilot and say "build me a URL shortener." The AI asks 20 questions, makes random tech choices, and builds something different than what you imagined.

## The Solution

Forge creates a `.forge/` folder with two files:
- **spec.md** — What you want (you fill this in)
- **rules.md** — How to build it (sensible defaults)

Your AI reads these files and builds exactly what you described.

## Quick Start

```bash
# Install
pip install forge-ai

# Create a project
forge new my-app
cd my-app

# Edit the spec with your idea
vim .forge/spec.md

# Tell your AI to build it
claude "Read .forge/spec.md and .forge/rules.md, then build this project"
```

That's it. Your AI now knows what to build and how.

## What Goes in spec.md?

```markdown
# Project: LinkShort

## What
A URL shortener that tracks clicks.

## Users
- People sharing links on social media

## Features
- Shorten any URL to a 6-character code
- Track clicks with timestamp and country
- Simple dashboard showing stats

## Vibe
Fast, minimal, no sign-up required.
```

Write it like you're explaining to a friend. The AI figures out the rest.

## What's in rules.md?

Sensible defaults that keep your AI from over-engineering:

```markdown
# Build Rules

## Constraints
- Use free tiers only
- Single deployable unit
- Prefer SQLite for data

## Tech Preferences
- Boring, proven technology
- Minimize dependencies
- Simple over scalable
```

Edit these if you have specific preferences.

## Templates

Start faster with pre-configured specs:

```bash
forge new my-app --template web-app      # React + FastAPI + SQLite
forge new my-api --template api-only     # REST API + SQLite
forge new my-bot --template slack-bot    # Slack bot
forge new my-bot --template discord-bot  # Discord bot
```

## Commands

```bash
forge new <name>           # Create new project
forge new <name> -t <tpl>  # Create from template
forge init                 # Add .forge/ to existing project
forge dev                  # Run local dev server
forge publish              # Push to GitHub
```

## For Sundai Club

Track your build day:

```bash
forge sprint start    # Start timer
forge sprint status   # Check progress
forge sprint wrap     # Generate summary
forge demo <url>      # QR code for demos
```

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   .forge/       │     │   Your LLM      │     │   Your App      │
│   spec.md       │ ──▶ │   (Claude,      │ ──▶ │   (Built to     │
│   rules.md      │     │    Cursor, etc) │     │    your spec)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     You write            AI reads & builds        You ship
```

Forge doesn't call any AI APIs. It just creates the structure. You use whatever AI tool you already have.

## Install

**Option 1: pip**
```bash
pip install forge-ai
```

**Option 2: Clone**
```bash
git clone https://github.com/sundai-club/forge
cd forge
./setup.sh
source venv/bin/activate
```

## Works With

- Claude Code (`claude`)
- Cursor
- GitHub Copilot
- Aider
- Any LLM that can read files

## License

MIT
