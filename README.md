# Forge

**Turn your project idea into code using AI — without the back-and-forth.**

You know when you ask ChatGPT or Claude to build something, and it asks you 20 questions? Or makes weird tech choices? Forge fixes that by giving AI the context it needs upfront.

---

## What Does Forge Do?

Forge creates a folder with simple text files that describe your project. When you give these files to an AI (like Claude, Cursor, or Copilot), it knows exactly what to build.

```
your-project/
└── .forge/
    ├── spec.md      ← Describe your idea here (you fill this in)
    ├── rules.md     ← Tech choices & constraints (sensible defaults)
    ├── prompts.md   ← Copy-paste commands for AI
    └── deploy.md    ← How to put it online
```

**Before Forge:** "Build me a todo app" → AI asks 20 questions, picks random tech, builds wrong thing

**After Forge:** AI reads your spec, follows your rules, builds what you actually want

---

## Getting Started (5 minutes)

### Step 1: Install Forge

```bash
pip install forge-ai
```

Don't have Python? [Install it first](https://www.python.org/downloads/) (choose version 3.10 or higher).

### Step 2: Create Your Project

```bash
forge new my-app --interactive
```

You'll see a menu like this:
```
Available templates:

  1. web-app      - Full-stack web app (React + FastAPI + SQLite)
  2. api-only     - REST API backend (FastAPI + SQLite)
  3. ai-app       - AI/LLM application (OpenAI/Anthropic + chat UI)
  4. chrome-ext   - Chrome browser extension (Manifest V3)
  5. cli-tool     - Command-line tool (Click/Typer + packaging)
  6. data-viz     - Dashboard/visualization (Streamlit or React + charts)
  7. slack-bot    - Slack bot (slack-bolt)
  8. discord-bot  - Discord bot (discord.py)
  9. (blank)      - Start from scratch

Choose a template (1-9):
```

**Pick the one closest to your idea.** Not sure? Start with `web-app` for most projects.

### Step 3: Describe Your Idea

```bash
cd my-app
```

Open the file `.forge/spec.md` in any text editor (VS Code, Notepad, whatever you use).

You'll see something like this:
```markdown
# Project: [Your App Name]

## What
[A web application that does X for Y users]

## Users
- [Primary user type]

## Features
- [ ] User-facing feature 1
- [ ] User-facing feature 2
```

**Fill it in with your idea.** Here's an example:

```markdown
# Project: StudyBuddy

## What
A flashcard app that helps students memorize vocabulary.

## Users
- Students studying for exams
- Language learners

## Features
- [ ] Create flashcard decks with terms and definitions
- [ ] Quiz mode that shows term, user guesses definition
- [ ] Track which cards you get wrong most often
- [ ] Simple, clean design that works on phone

## Vibe
Simple, distraction-free, encouraging
```

**The more specific you are, the better the AI will build it.**

### Step 4: Tell AI to Build It

Now give your project to an AI. Here are the commands for different tools:

**Claude Code (Terminal):**
```bash
claude "Read .forge/spec.md and .forge/rules.md, then build this project step by step"
```

**Cursor:**
1. Open your project folder in Cursor
2. Press `Cmd+I` (Mac) or `Ctrl+I` (Windows) to open Composer
3. Type: `Read .forge/spec.md and .forge/rules.md, then build this project`

**ChatGPT / Claude.ai (Browser):**
1. Copy the contents of `.forge/spec.md` and `.forge/rules.md`
2. Paste them into the chat
3. Say: "Build this project step by step"

**Aider:**
```bash
aider --read .forge/spec.md --read .forge/rules.md
```

### Step 5: Run Your App

The AI will create files and tell you how to run them. Usually it's something like:

```bash
# For web apps
cd frontend && npm install && npm run dev

# For Python apps
pip install -r requirements.txt
python main.py
```

---

## Which Template Should I Use?

| I want to build... | Use this template |
|-------------------|-------------------|
| A website with user accounts, database, etc. | `web-app` |
| Just a backend/API (no frontend) | `api-only` |
| A ChatGPT-style AI chat app | `ai-app` |
| A Chrome browser extension | `chrome-ext` |
| A command-line tool | `cli-tool` |
| Charts, graphs, data dashboard | `data-viz` |
| A Slack bot | `slack-bot` |
| A Discord bot | `discord-bot` |
| Something else entirely | `(blank)` |

---

## Common Questions

### "I don't know what to put in spec.md"

Just write what you'd tell a friend. Be specific about:
- **What** does it do?
- **Who** is it for?
- **What features** should it have?

Bad: "A social media app"
Good: "An app where users can post photos, follow other users, and like/comment on posts. Similar to Instagram but simpler."

### "The AI built something different than I wanted"

Your spec probably wasn't specific enough. Add more detail:
- What should each button do?
- What happens when someone clicks X?
- What data needs to be saved?

Then tell the AI: `Read .forge/spec.md again. I updated it. Rebuild the [specific part] to match.`

### "How do I add a feature?"

```bash
claude "Read .forge/spec.md. Add [describe your feature] following the rules in .forge/rules.md"
```

### "How do I fix a bug?"

```bash
claude "The app has this problem: [describe what's wrong]. Fix it."
```

### "How do I put it online?"

Check `.forge/deploy.md` in your project — it has step-by-step instructions for your specific template.

### "I want different tech choices"

Edit `.forge/rules.md` to change the tech stack. For example, change "React" to "Vue" or "FastAPI" to "Flask".

---

## All Commands

```bash
forge new my-project              # Create project (asks for template)
forge new my-project -t web-app   # Create with specific template
forge new --interactive           # Interactive mode with menu
forge templates                   # List all available templates
forge init                        # Add .forge/ to existing project
forge publish                     # Push to GitHub
```

---

## Example: Building a Todo App

```bash
# 1. Create project
forge new todo-app -t web-app
cd todo-app

# 2. Edit .forge/spec.md with this:
```

```markdown
# Project: SimpleTodo

## What
A minimal todo list app. No accounts, just a list that saves to the browser.

## Users
- Anyone who wants a quick todo list

## Features
- [ ] Add todos with a text input
- [ ] Mark todos as complete (strikethrough)
- [ ] Delete todos
- [ ] Todos persist when you refresh the page (localStorage)

## Vibe
Super minimal. Just a text input and a list. No clutter.
```

```bash
# 3. Build it
claude "Read .forge/spec.md and .forge/rules.md, then build this project"

# 4. Run it
cd frontend && npm install && npm run dev
```

---

## Tips for Best Results

1. **Be specific** — "Blue button in the top right" not "a button somewhere"
2. **Include examples** — "Like Spotify's playlist page" helps AI understand
3. **Start small** — Get basic version working, then add features
4. **Iterate** — Build → Test → Improve → Repeat

---

## Need Help?

- Check `.forge/prompts.md` in your project for copy-paste AI commands
- See [HACKATHON.md](HACKATHON.md) for hackathon-specific tips
- [Report issues on GitHub](https://github.com/sundai-club/forge/issues)

---

## Install Options

**pip (recommended):**
```bash
pip install forge-ai
```

**From source:**
```bash
git clone https://github.com/sundai-club/forge
cd forge
pip install -e .
```

---

Made with coffee by [Sundai Club](https://sundai.club)
