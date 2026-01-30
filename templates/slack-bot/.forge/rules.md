# Build Rules

## Stack
- Framework: Python with slack-bolt
- Database: SQLite (if needed)

## Structure
```
/
├── main.py            # Bot entry point
├── handlers/          # Command handlers
├── requirements.txt
└── README.md
```

## Slack Setup Required
1. Create app at api.slack.com/apps
2. Enable Socket Mode or use HTTP
3. Add bot scopes: chat:write, commands, app_mentions:read
4. Install to workspace
5. Copy tokens to .env

## Environment Variables
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...  # For Socket Mode
SLACK_SIGNING_SECRET=...   # For HTTP mode
```

## Constraints
- Use slack-bolt library
- Respond within 3 seconds (Slack timeout)
- Use blocks for rich formatting
- Handle errors gracefully

## Response Rules
- Keep responses concise
- Use threading for long outputs
- Include helpful error messages
- Acknowledge commands immediately

## Deploy Target
- Railway or Render (always-on needed)
- Or use Socket Mode for development
