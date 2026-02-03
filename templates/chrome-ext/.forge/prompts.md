# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this Chrome extension step by step. Start with manifest.json, then popup, then content script."
```

## Add a feature
```bash
claude "Read .forge/spec.md. Add [describe feature] following the rules in .forge/rules.md."
```

## Fix an issue
```bash
claude "Read .forge/spec.md. The extension has this bug: [describe bug]. Fix it."
```

## Add popup UI
```bash
claude "Read .forge/spec.md and rules.md. Create a popup with [describe UI elements]."
```

## Add content script
```bash
claude "Read .forge/spec.md. Add a content script that [describe what it should do on the page]."
```

## Add storage
```bash
claude "Read .forge/spec.md. Add chrome.storage to save [describe what to save] and load it when the extension opens."
```

## Add messaging
```bash
claude "Read .forge/spec.md. Add message passing between the popup and content script so they can [describe communication need]."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this Chrome extension following rules.md"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this Chrome extension step by step
```

---

## Testing Your Extension

```bash
# After building, load it in Chrome:
1. Open chrome://extensions
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select your extension folder
5. Click the extension icon to test
```

---

## Tips

- **Test early**: Load the extension after each change
- **Check console**: Right-click popup > Inspect for errors
- **Reload often**: Click refresh icon in chrome://extensions after changes
- **Start minimal**: Get popup working before content scripts
