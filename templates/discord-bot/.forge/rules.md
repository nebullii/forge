# Build Rules

## Stack
- Framework: discord.py (Python 3.10+)
- Database: SQLite (if needed)

## Structure
```
/
├── main.py            # Bot entry point
├── cogs/              # Command groups
├── requirements.txt
└── README.md
```

## Discord Setup Required
1. Create app at discord.com/developers
2. Create bot user
3. Enable required intents
4. Generate invite URL with permissions
5. Copy bot token to .env

## Environment Variables
```
DISCORD_TOKEN=...
DISCORD_GUILD_ID=...  # Optional: for dev server
```

## Constraints
- Use discord.py 2.0+ with slash commands
- Use Cogs for organization
- Handle rate limits gracefully
- SQLite for any persistence

## Command Rules
- Use slash commands (not prefix)
- Include command descriptions
- Add proper error handling
- Use embeds for rich responses

## Response Rules
- Keep responses under 2000 chars
- Use embeds for structured data
- Include helpful error messages
- React to acknowledge when appropriate

## Deploy Target
- Railway or Render (always-on needed)
- Needs persistent connection
