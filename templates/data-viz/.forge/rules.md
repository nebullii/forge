# Build Rules

## Stack Options

### Option A: Streamlit (Fastest)
- Framework: Streamlit
- Charts: Plotly or Altair
- Best for: Quick prototypes, data science

### Option B: React Dashboard
- Frontend: React + Vite
- Charts: Recharts or Chart.js
- Backend: FastAPI (if needed)
- Best for: Custom UI, complex interactions

## Structure (Streamlit)
```
/
├── app.py              # Main Streamlit app
├── pages/              # Multi-page app
│   ├── 1_Overview.py
│   └── 2_Details.py
├── data/               # Data files
│   └── sample.csv
├── utils/              # Helper functions
│   └── data_loader.py
├── requirements.txt
└── README.md
```

## Structure (React)
```
/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Chart.jsx
│   │   │   └── FilterBar.jsx
│   │   └── App.jsx
│   └── package.json
├── backend/            # Optional
│   ├── main.py
│   └── requirements.txt
├── data/
│   └── sample.csv
└── README.md
```

## Streamlit Pattern
```python
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("My Dashboard")

# Load data
@st.cache_data
def load_data():
    return pd.read_csv("data/sample.csv")

df = load_data()

# Filters
col1, col2 = st.columns(2)
with col1:
    date_filter = st.date_input("Date range")
with col2:
    category = st.selectbox("Category", df["category"].unique())

# Chart
fig = px.line(df, x="date", y="value", title="Trend")
st.plotly_chart(fig, use_container_width=True)
```

## React + Recharts Pattern
```jsx
import { LineChart, Line, XAxis, YAxis, Tooltip } from 'recharts';

function Chart({ data }) {
  return (
    <LineChart width={600} height={300} data={data}>
      <XAxis dataKey="date" />
      <YAxis />
      <Tooltip />
      <Line type="monotone" dataKey="value" stroke="#8884d8" />
    </LineChart>
  );
}
```

## Constraints
- Handle missing/null data gracefully
- Optimize for large datasets (sampling, aggregation)
- Mobile-responsive charts
- Fast initial load (< 3 seconds)

## Chart Best Practices
- Clear titles and labels
- Consistent color scheme
- Appropriate chart types for data
- Don't overcrowd with too many series
- Include legends when needed

## Data Handling
```python
# Streamlit caching
@st.cache_data
def load_data():
    return pd.read_csv("data.csv")

# Handle large files
df = pd.read_csv("large.csv", nrows=10000)  # Sample
```

## Interactivity Rules
- Filters update all charts
- Loading states for data fetches
- Preserve filter state on refresh
- Mobile-friendly filter controls

## Color Palette
```python
# Consistent colors
COLORS = {
    "primary": "#3B82F6",
    "secondary": "#10B981",
    "accent": "#F59E0B",
    "danger": "#EF4444",
    "neutral": "#6B7280"
}
```

## Deploy Target

### Streamlit
- Streamlit Cloud (free, easiest)
- Connect GitHub repo, auto-deploys

### React
- Vercel or Netlify (frontend)
- Railway if backend needed
