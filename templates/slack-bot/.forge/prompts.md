# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this Slack bot step by step. Start with the main bot setup, then add command handlers."
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
claude "Read .forge/spec.md. Add handling for [message/app_mention/reaction] events."
```

## Add rich formatting
```bash
claude "Read .forge/spec.md. Update the bot responses to use Slack blocks for better formatting."
```

## Add database
```bash
claude "Read .forge/spec.md and rules.md. Add SQLite to store [describe what to store]."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this Slack bot following rules.md"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this Slack bot step by step
```

---

## Tips

- **Test in Slack**: Create a test workspace or channel
- **Respond fast**: Slack expects response in 3 seconds
- **Use blocks**: Rich formatting looks more professional
- **Handle errors**: Bot should never crash silently
