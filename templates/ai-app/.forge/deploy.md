# Deployment Guide

## Option 1: Railway (Recommended)

Best for AI apps because it handles secrets well.

1. Go to [railway.app](https://railway.app)
2. Click "New Project" > "Deploy from GitHub"
3. Select your repo
4. **Important**: Add API keys as environment variables:
   ```
   OPENAI_API_KEY=sk-...
   # or
   ANTHROPIC_API_KEY=sk-ant-...
   ```
5. Get your public URL

---

## Option 2: Vercel + Railway

### Backend (Railway)
1. Deploy backend to Railway
2. Add API keys as environment variables
3. Copy the deployed URL

### Frontend (Vercel)
1. Deploy frontend to Vercel
2. Add `VITE_API_URL` pointing to Railway backend
3. Deploy

---

## Option 3: Render

1. Go to [render.com](https://render.com)
2. Click "New" > "Web Service"
3. Connect GitHub repo
4. Configure:
   - Build command: `pip install -r backend/requirements.txt`
   - Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. **Important**: Add API keys in "Environment" section
6. Deploy

---

## Environment Variables

**Required** (set in deployment platform, NOT in code):

```
OPENAI_API_KEY=sk-...           # If using OpenAI
ANTHROPIC_API_KEY=sk-ant-...    # If using Anthropic
TOGETHER_API_KEY=...            # If using Together

# Optional
MAX_TOKENS_PER_REQUEST=1000
DAILY_TOKEN_LIMIT=100000
```

**Never commit API keys to git!**

---

## Cost Control in Production

1. Set token limits per request
2. Add daily usage caps
3. Monitor usage in provider dashboard
4. Use cheaper models (gpt-4o-mini, claude-3-haiku)

---

## Quick Deploy Button

Add to your README:

```markdown
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=YOUR_TEMPLATE)
```

---

## Post-Deploy Checklist

- [ ] App loads without errors
- [ ] Chat sends and receives messages
- [ ] API key is set (not exposed in frontend)
- [ ] Error messages show when API fails
- [ ] Token limits are configured
- [ ] Streaming works (if implemented)
