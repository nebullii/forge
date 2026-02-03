# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this project step by step, starting with the backend then frontend."
```

## Add a feature
```bash
claude "Read .forge/spec.md. Add [describe feature] following the rules in .forge/rules.md."
```

## Fix an issue
```bash
claude "Read .forge/spec.md. The app has this bug: [describe bug]. Fix it."
```

## Improve the UI
```bash
claude "Read .forge/spec.md. Improve the UI to be more [modern/minimal/polished]. Keep the same functionality."
```

## Add tests
```bash
claude "Read the codebase. Add tests for the main functionality."
```

## Prepare for demo
```bash
claude "Read .forge/spec.md. Add sample data and polish the UI for a demo."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this project following rules.md"

Or use Composer:
1. Press `Cmd+I` to open Composer
2. Type: "Read .forge/spec.md and rules.md, build this project"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this project step by step
```

---

## Tips

- **Be specific**: "Add user login with email/password" > "Add auth"
- **One thing at a time**: Don't ask for 5 features at once
- **Iterate**: Build basic version first, then improve
- **Check the output**: Review code before running
