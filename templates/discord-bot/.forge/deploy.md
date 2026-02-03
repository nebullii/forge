# Deployment Guide

## Option 1: Railway (Recommended)

Discord bots need to run 24/7, Railway handles this well.

1. Go to [railway.app](https://railway.app)
2. Click "New Project" > "Deploy from GitHub"
3. Select your repo
4. Add environment variables:
   ```
   DISCORD_TOKEN=...
   ```
5. Deploy

Railway will keep your bot running.

---

## Option 2: Render

1. Go to [render.com](https://render.com)
2. Click "New" > "Background Worker" (not Web Service)
3. Connect GitHub repo
4. Configure:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python main.py`
5. Add environment variables
6. Deploy

---

## Option 3: Fly.io

```bash
# Install flyctl
brew install flyctl

# Launch
fly launch

# Set secrets
fly secrets set DISCORD_TOKEN=...

# Deploy
fly deploy
```

---

## Discord Developer Portal

1. Go to discord.com/developers/applications
2. Select your application
3. Go to Bot section
4. Copy the token (keep it secret!)
5. Enable required Intents:
   - Presence Intent (if needed)
   - Server Members Intent (if needed)
   - Message Content Intent (if reading messages)

---

## Invite Your Bot

1. Go to OAuth2 > URL Generator
2. Select scopes: `bot`, `applications.commands`
3. Select permissions your bot needs
4. Copy the generated URL
5. Open URL in browser to add bot to server

---

## Environment Variables

```
DISCORD_TOKEN=...              # Bot token from Developer Portal
DISCORD_GUILD_ID=...           # Optional: for development server
```

---

## Post-Deploy Checklist

- [ ] Bot comes online in Discord
- [ ] Slash commands appear
- [ ] Commands respond correctly
- [ ] Bot stays online (check logs)
- [ ] Error handling works

---

## Debugging

```bash
# Check Railway logs
railway logs

# Check Render logs
# Go to dashboard > Service > Logs
```

---

## Note for Hackathons

For demos, your bot just needs to be running. Add it to a test server and demo from there. No need for public bot verification.
