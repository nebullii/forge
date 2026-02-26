# Deployment Guide

## Render (Recommended)

Best for full-stack apps with a `render.yaml` Blueprint.

### Using render.yaml (one-click)

1. Add a `render.yaml` to your project root:
   ```yaml
   services:
     - type: web
       name: my-app-backend
       runtime: python
       buildCommand: pip install -r backend/requirements.txt
       startCommand: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
       envVars:
         - key: OPENAI_API_KEY
           sync: false

     - type: web
       name: my-app-frontend
       runtime: static
       buildCommand: cd frontend && npm install && npm run build
       staticPublishPath: frontend/dist
       envVars:
         - key: VITE_API_URL
           sync: false
       routes:
         - type: rewrite
           source: /*
           destination: /index.html
   ```
2. Go to [render.com](https://render.com) > "New" > "Blueprint"
3. Connect your GitHub repo -- Render reads `render.yaml` automatically
4. Set environment variables when prompted:
   - `OPENAI_API_KEY` -- your API key
   - `VITE_API_URL` -- the backend service URL (e.g. `https://my-app-backend.onrender.com`)
5. Deploy

### Manual setup

1. **Backend**: "New" > "Web Service"
   - Build: `pip install -r backend/requirements.txt`
   - Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Add `OPENAI_API_KEY` in Environment tab
2. **Frontend**: "New" > "Static Site"
   - Build: `cd frontend && npm install && npm run build`
   - Publish dir: `frontend/dist`
   - Add `VITE_API_URL` pointing to backend URL
   - Add rewrite rule: `/*` -> `/index.html`

---

## Alternative: Railway

1. Go to [railway.app](https://railway.app)
2. "New Project" > "Deploy from GitHub"
3. Add API keys as environment variables
4. Get your public URL

---

## Environment Variables

**Required** (set in deployment platform, NOT in code):

```
OPENAI_API_KEY=sk-...           # If using OpenAI
ANTHROPIC_API_KEY=sk-ant-...    # If using Anthropic
VITE_API_URL=https://...        # Backend URL for frontend
```

**Never commit API keys to git!**

---

## Post-Deploy Checklist

- [ ] Backend health check responds (`/api/health`)
- [ ] Frontend loads and dropdown populates
- [ ] AI analysis generates on team selection
- [ ] API key is set (not exposed in frontend)
- [ ] Error messages show when API fails
- [ ] Client-side caching works (localStorage)
