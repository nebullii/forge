# Hackathon Guide

Get from idea to demo faster with Forge.

## Quick Start (First 15 minutes)

```bash
# 1. Create your project
forge new my-hack --interactive   # Pick a template
cd my-hack

# 2. Fill in your spec (5 min)
# Edit .forge/spec.md with your idea

# 3. Start building
claude "Read .forge/spec.md and .forge/rules.md, then build this project"
```

## Recommended Templates

| Template | Best for |
|----------|----------|
| `ai-app` | ChatGPT wrapper, AI assistant, LLM tool |
| `web-app` | Full-stack app with database |
| `chrome-ext` | Browser productivity tool, quick demo |
| `data-viz` | Data dashboard, charts, analytics |
| `cli-tool` | Developer tool, automation script |
| `api-only` | Backend for mobile app, webhook handler |

## Team Setup

### Same Repo, Multiple People

```bash
# Person 1: Create and push
forge new team-project -t web-app
cd team-project
git init && git add . && git commit -m "Initial commit"
gh repo create team-project --public --source=. --push

# Person 2, 3, etc: Clone
git clone https://github.com/yourteam/team-project
cd team-project
```

### Divide and Conquer

Split the work in spec.md:
```markdown
## Features
- [ ] Feature 1 (Alice)
- [ ] Feature 2 (Bob)
- [ ] Feature 3 (Charlie)
```

Each person focuses on their feature, merges often.

## Time Management

### 4-Hour Hackathon
- **Hour 1**: Pick template, fill spec, get basic app running
- **Hour 2-3**: Build core features, iterate with AI
- **Hour 4**: Polish UI, deploy, prep demo

### 24-Hour Hackathon
- **First 2 hours**: Idea, template, spec, basic prototype
- **Hours 3-12**: Build all features, test, iterate
- **Hours 12-20**: Polish, edge cases, deployment
- **Last 4 hours**: Demo prep, practice pitch, sleep

## Common Pitfalls

### "AI keeps asking questions"
Your spec is too vague. Add more detail:
```markdown
# Bad
A tool that helps with tasks

# Good
A todo app where users can:
- Add tasks with a title and due date
- Mark tasks complete
- Filter by completed/incomplete
- Data persists in SQLite
```

### "It's building the wrong thing"
Stop and update spec.md. Be explicit about what you want. The AI reads the spec fresh each time.

### "I'm stuck on deployment"
Check `.forge/deploy.md` in your project. Each template has specific deploy instructions.

### "We have merge conflicts"
Work on different files when possible. Commit and push often. Talk to your teammates.

## "Ship It" Mentality

### What matters at hackathons:
1. **Something that works** (demo the happy path)
2. **Clear value prop** (solve a real problem)
3. **Good presentation** (2-minute pitch)

### What doesn't matter:
- Perfect code
- 100% test coverage
- Production-ready infrastructure
- Error handling for edge cases

### When in doubt, cut scope
Better to have 2 polished features than 5 broken ones.

## Demo Prep

### Before you present
```bash
# Check your demo prep list
cat .forge/demo-checklist.md

# Start your pitch template
cat .forge/pitch.md
```

### The 2-minute pitch
1. **Problem** (30 sec): What pain point?
2. **Demo** (60 sec): Show it working
3. **Tech** (20 sec): One interesting choice
4. **Next** (10 sec): What's next if you kept building

### If it breaks during demo
1. Don't panic
2. Have backup screenshots
3. Explain what it would have done
4. Focus on what you learned

## Pro Tips

### Speed up iteration
```bash
# Run AI, see output, adjust spec, repeat
claude "Read .forge/spec.md. Add [small feature]."
```

### Use the sprint timer
```bash
forge sprint start   # Start timer
forge sprint status  # Check time
forge sprint wrap    # Generate summary
```

### Deploy early
Don't wait until the end. Deploy a basic version after hour 1. Update it as you go.

### Backup your work
```bash
git add . && git commit -m "Save point" && git push
```

Commit often. You can always revert.

## Template Cheat Sheet

### ai-app
- OpenAI/Anthropic API
- Chat interface
- Streaming responses
- Deploy: Railway

### web-app
- React frontend
- FastAPI backend
- SQLite database
- Deploy: Vercel + Railway

### chrome-ext
- Manifest V3
- Popup + content script
- Chrome storage
- Deploy: Load unpacked

### data-viz
- Streamlit or React
- Plotly/Recharts
- CSV/API data
- Deploy: Streamlit Cloud

### cli-tool
- Click/Typer
- Rich output
- pip installable
- Deploy: PyPI

Good luck! Ship something cool.
