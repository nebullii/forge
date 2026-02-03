# Deployment Guide

## Streamlit App

### Option 1: Streamlit Cloud (Recommended)

Free and easiest for Streamlit apps.

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click "New app"
4. Select your repo and branch
5. Set main file path (e.g., `app.py`)
6. Click "Deploy"

Auto-redeploys on every push to main branch.

### Option 2: Railway
```bash
# Add to requirements.txt
streamlit

# Create Procfile
web: streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

Then deploy to Railway as usual.

---

## React Dashboard

### Option 1: Vercel (Frontend Only)

If your dashboard uses static data or client-side API calls:

```bash
cd frontend
npm run build
npx vercel
```

Or connect GitHub for auto-deploys at [vercel.com](https://vercel.com).

### Option 2: Vercel + Railway (With Backend)

1. Deploy backend (FastAPI) to Railway
2. Deploy frontend to Vercel
3. Set `VITE_API_URL` in Vercel to your Railway URL

### Option 3: Railway (Full Stack)

Deploy everything on Railway:
1. Connect GitHub repo
2. Set build commands for frontend + backend
3. Configure environment variables

---

## Data Files

### Static Data (CSV in repo)
```python
# Works on Streamlit Cloud
import pandas as pd
df = pd.read_csv("data/sample.csv")
```

### External Data (API)
```python
# Set API keys as secrets in deployment platform
import os
api_key = os.getenv("DATA_API_KEY")
```

### Database
- Streamlit Cloud: Use external DB (Supabase, PlanetScale)
- Railway: Add PostgreSQL service

---

## Quick Deploy Buttons

Add to your README:

### Streamlit
```markdown
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/YOUR_USERNAME/YOUR_REPO/main/app.py)
```

### Vercel
```markdown
[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=YOUR_REPO_URL)
```

---

## Post-Deploy Checklist

- [ ] Dashboard loads without errors
- [ ] All charts render correctly
- [ ] Data loads successfully
- [ ] Filters work as expected
- [ ] Mobile view looks acceptable
- [ ] Loading states show properly
