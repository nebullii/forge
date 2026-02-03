# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this Discord bot step by step. Start with the main bot setup, then add command handlers."
```

## Add a command
```bash
claude "Read .forge/spec.md. Add a new slash command: [describe command] following the rules in .forge/rules.md."
```

## Fix an issue
```bash
claude "Read .forge/spec.md. The bot has this bug: [describe bug]. Fix it."
```

## Add event handling
```bash
claude "Read .forge/spec.md. Add handling for [message/reaction/member_join] events."
```

## Add embeds
```bash
claude "Read .forge/spec.md. Update the bot responses to use Discord embeds for better formatting."
```

## Add database
```bash
claude "Read .forge/spec.md and rules.md. Add SQLite to store [describe what to store]."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this Discord bot following rules.md"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this Discord bot step by step
```

---

## Tips

- **Test server**: Create a private server for testing
- **Use slash commands**: They have better UX than prefix commands
- **Add embeds**: Rich formatting looks more professional
- **Handle permissions**: Check bot has required permissions
