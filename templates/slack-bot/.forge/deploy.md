# Deployment Guide

## Option 1: Railway (Recommended)

Slack bots need to run 24/7, Railway handles this well.

1. Go to [railway.app](https://railway.app)
2. Click "New Project" > "Deploy from GitHub"
3. Select your repo
4. Add environment variables:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_SIGNING_SECRET=...
   ```
5. Deploy

Railway will keep your bot running.

---

## Option 2: Render

1. Go to [render.com](https://render.com)
2. Click "New" > "Web Service"
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
fly secrets set SLACK_BOT_TOKEN=xoxb-...
fly secrets set SLACK_APP_TOKEN=xapp-...

# Deploy
fly deploy
```

---

## Slack App Configuration

### For Socket Mode (Recommended for hackathons)
1. Go to api.slack.com/apps
2. Select your app
3. Enable Socket Mode
4. Generate App-Level Token (xapp-...)
5. Use this token in your bot

### For HTTP Mode (Production)
1. Set Request URL to: `https://your-app.railway.app/slack/events`
2. Enable Event Subscriptions
3. Subscribe to bot events

---

## Environment Variables

```
SLACK_BOT_TOKEN=xoxb-...        # Bot token
SLACK_APP_TOKEN=xapp-...        # App token (Socket Mode)
SLACK_SIGNING_SECRET=...        # Signing secret (HTTP Mode)
```

Get these from api.slack.com/apps > Your App.

---

## Post-Deploy Checklist

- [ ] Bot comes online in Slack
- [ ] Slash commands respond
- [ ] Events are received
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
