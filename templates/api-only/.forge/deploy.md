# Deployment Guide

## Option 1: Railway (Recommended)

Fastest option for Python APIs.

1. Go to [railway.app](https://railway.app)
2. Click "New Project" > "Deploy from GitHub"
3. Select your repo
4. Railway auto-detects Python
5. Add environment variables in dashboard
6. Get your public URL

Railway auto-runs: `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## Option 2: Render

1. Go to [render.com](https://render.com)
2. Click "New" > "Web Service"
3. Connect GitHub repo
4. Configure:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables
6. Deploy

---

## Option 3: Fly.io

```bash
# Install flyctl
brew install flyctl

# Deploy
fly launch
fly deploy
```

---

## Environment Variables

Set these in your deployment platform:

```
DATABASE_URL=sqlite:///./app.db
SECRET_KEY=your-secret-key
# Add your app-specific vars
```

---

## Quick Deploy Button

Add to your README:

```markdown
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=YOUR_TEMPLATE)
```

---

## API Documentation

Your FastAPI docs are available at:
- `https://your-app.railway.app/docs` (Swagger UI)
- `https://your-app.railway.app/redoc` (ReDoc)

---

## Post-Deploy Checklist

- [ ] Health check endpoint works: `GET /api/health`
- [ ] All CRUD endpoints respond
- [ ] Database persists between deploys
- [ ] Environment variables are set
- [ ] Rate limiting is configured (if needed)
