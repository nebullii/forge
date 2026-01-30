# Sundai Club Quick Start

Ship a project in one day. Forge sets up the structure, you bring your LLM.

## Setup (2 min)

```bash
git clone https://github.com/sundai-club/forge && cd forge
./setup.sh
source venv/bin/activate
```

## Build Day Flow

```bash
# Create project
forge new my-idea --template web-app
cd my-idea

# Start timer
forge sprint start

# Edit your spec
vim .forge/spec.md

# Build with your LLM
claude "Read .forge/spec.md and .forge/rules.md, then build this project"

# Test locally
forge dev

# Demo
forge demo https://your-deployed-url.com

# Push to GitHub
forge publish

# Wrap up
forge sprint wrap
```

## Templates

```bash
forge new app --template web-app     # React + FastAPI
forge new api --template api-only    # REST API + SQLite
forge new bot --template slack-bot   # Slack bot
forge new bot --template discord-bot # Discord bot
```

## Commands

| Command | What it does |
|---------|--------------|
| `forge new <name>` | Create project |
| `forge new <name> -t <template>` | Create from template |
| `forge init` | Add .forge/ to current dir |
| `forge dev` | Local dev server |
| `forge demo <url>` | Generate QR code |
| `forge publish` | Push to GitHub |
| `forge sprint start` | Start timer |
| `forge sprint status` | Check progress |
| `forge sprint wrap` | Generate summary |

## Tips

1. Write a clear spec - the LLM builds what you describe
2. Keep it simple - one feature at a time
3. Test early - run `forge dev` often
4. Ship it - done is better than perfect
