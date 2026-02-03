# Deployment Guide

## Option 1: Vercel + Railway (Recommended)

### Frontend (Vercel)
```bash
# Install Vercel CLI
npm i -g vercel

# Deploy frontend
cd frontend
vercel
```

Or connect GitHub repo at [vercel.com](https://vercel.com) for auto-deploys.

### Backend (Railway)
1. Go to [railway.app](https://railway.app)
2. Click "New Project" > "Deploy from GitHub"
3. Select your repo
4. Set root directory to `backend`
5. Add environment variables in Railway dashboard
6. Copy the deployed URL

### Connect Frontend to Backend
Update frontend API calls to use Railway URL:
```javascript
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

Add `VITE_API_URL` to Vercel environment variables.

---

## Option 2: Railway (Full Stack)

Deploy everything on Railway:

1. Go to [railway.app](https://railway.app)
2. Click "New Project" > "Deploy from GitHub"
3. Railway auto-detects Python backend
4. Add environment variables
5. Get your public URL

For frontend, either:
- Build frontend and serve from FastAPI
- Or create separate Railway service

---

## Option 3: Render

1. Go to [render.com](https://render.com)
2. Click "New" > "Web Service"
3. Connect GitHub repo
4. Configure:
   - Build command: `pip install -r backend/requirements.txt`
   - Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables
6. Deploy

---

## Environment Variables

Set these in your deployment platform:

```
DATABASE_URL=sqlite:///./app.db  # Or your DB URL
SECRET_KEY=your-secret-key
# Add your app-specific vars
```

---

## Quick Deploy Buttons

Add to your README:

```markdown
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/your-template)

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=YOUR_REPO_URL)
```

---

## Post-Deploy Checklist

- [ ] App loads without errors
- [ ] API endpoints respond
- [ ] Database persists data
- [ ] Environment variables are set
- [ ] CORS is configured for frontend URL
