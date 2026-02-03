# Forge

Give your AI the structure it needs to build your project.

## 30-Second Quick Start

```bash
pip install forge-ai
forge new my-app --template ai-app
cd my-app
# Edit .forge/spec.md with your idea, then:
claude "Read .forge/spec.md and .forge/rules.md, then build this project"
```

That's it. Your AI now knows what to build and how.

## What It Does

Forge creates a `.forge/` folder with files that guide your AI:

```
my-app/
└── .forge/
    ├── spec.md      ← What you want (you edit this)
    ├── rules.md     ← How to build it (sensible defaults)
    ├── prompts.md   ← Copy-paste AI commands
    └── deploy.md    ← Deployment guide
```

No more 20 questions from your AI. No random tech choices. Just structured context that produces consistent results.

## Templates

```bash
forge templates                    # List all templates
forge new my-app --interactive     # Interactive picker

# Or specify directly:
forge new my-app -t web-app        # React + FastAPI + SQLite
forge new my-api -t api-only       # REST API + SQLite
forge new my-ai  -t ai-app         # LLM chat app (OpenAI/Anthropic)
forge new my-ext -t chrome-ext     # Chrome extension
forge new my-cli -t cli-tool       # Command-line tool
forge new my-viz -t data-viz       # Dashboard/charts
forge new my-bot -t slack-bot      # Slack bot
forge new my-bot -t discord-bot    # Discord bot
```

## Commands

```bash
forge new <name>              # Create project
forge new <name> -t <template># Create from template
forge new --interactive       # Interactive mode
forge templates               # List templates
forge init                    # Add .forge/ to existing project
forge dev                     # Local dev server
forge publish                 # Push to GitHub
forge sprint start            # Start build timer
forge demo <url>              # Generate QR code
```

## Works With

- Claude Code (`claude`)
- Cursor
- GitHub Copilot
- Aider
- Any LLM that can read files

## Hackathon?

See [HACKATHON.md](HACKATHON.md) for tips on using Forge at hackathons.

## Install

```bash
# pip
pip install forge-ai

# or clone
git clone https://github.com/sundai-club/forge
cd forge && ./setup.sh
```

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   .forge/       │     │   Your AI       │     │   Your App      │
│   spec.md       │ ──▶ │   (Claude,      │ ──▶ │   (Built to     │
│   rules.md      │     │    Cursor, etc) │     │    your spec)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     You write            AI reads & builds        You ship
```

Forge doesn't call any AI APIs. It creates structure. You use whatever AI you have.

## License

MIT
