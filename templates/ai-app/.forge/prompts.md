# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this AI app step by step. Start with the backend API for chat, then the frontend chat UI."
```

## Add a feature
```bash
claude "Read .forge/spec.md. Add [describe feature] following the rules in .forge/rules.md."
```

## Fix an issue
```bash
claude "Read .forge/spec.md. The AI response has this issue: [describe issue]. Fix it."
```

## Improve the prompts
```bash
claude "Read backend/prompts/system.txt. The AI responses are [too long/not helpful/missing context]. Improve the system prompt."
```

## Add streaming
```bash
claude "Read .forge/spec.md and rules.md. Add streaming responses so the AI output appears word by word."
```

## Add conversation memory
```bash
claude "Read .forge/spec.md. Add conversation history so the AI remembers previous messages in the chat."
```

## Switch AI provider
```bash
claude "Read .forge/spec.md. Switch from OpenAI to Anthropic/Claude. Update the API calls and environment variables."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this AI app following rules.md"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this AI app step by step
```

---

## Tips

- **Test prompts first**: Try your system prompt in ChatGPT/Claude before coding
- **Start simple**: Get basic chat working before adding features
- **Watch costs**: Use cheap models (gpt-4o-mini, claude-3-haiku) for development
- **Handle errors**: API rate limits and timeouts will happen
