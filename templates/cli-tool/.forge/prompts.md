# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this CLI tool step by step. Start with the main CLI structure, then add subcommands."
```

## Add a command
```bash
claude "Read .forge/spec.md. Add a new command: [describe command] following the rules in .forge/rules.md."
```

## Fix an issue
```bash
claude "Read .forge/spec.md. The CLI has this bug: [describe bug]. Fix it."
```

## Add options/flags
```bash
claude "Read .forge/spec.md. Add these options to the [command] command: [describe options]."
```

## Add config file support
```bash
claude "Read .forge/spec.md and rules.md. Add support for reading settings from ~/.config/mytool/config.json."
```

## Add output formatting
```bash
claude "Read .forge/spec.md. Add --format option to output as JSON, CSV, or table."
```

## Make it installable
```bash
claude "Read .forge/spec.md. Set up pyproject.toml so the tool can be installed with 'pip install .'."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this CLI tool following rules.md"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this CLI tool step by step
```

---

## Testing Your CLI

```bash
# Install locally for testing
pip install -e .

# Run your tool
mytool --help
mytool [command] --help
```

---

## Tips

- **Help text matters**: Write clear command and option descriptions
- **Fail fast**: Validate inputs early, show helpful errors
- **Exit codes**: Return 0 for success, non-zero for errors
- **Test piping**: Make sure stdin/stdout work correctly
