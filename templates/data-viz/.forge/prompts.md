# AI Prompts

Copy-paste commands to build your project with AI.

## Build from scratch
```bash
claude "Read .forge/spec.md and .forge/rules.md. Build this dashboard step by step. Start with data loading, then create the main charts."
```

## Add a visualization
```bash
claude "Read .forge/spec.md. Add a [chart type] chart that shows [describe what it should show] following .forge/rules.md."
```

## Fix an issue
```bash
claude "Read .forge/spec.md. The dashboard has this bug: [describe bug]. Fix it."
```

## Add filters
```bash
claude "Read .forge/spec.md. Add filter controls for [describe what to filter by]. Update all charts when filters change."
```

## Improve chart styling
```bash
claude "Read .forge/spec.md. Improve the chart styling to look more [professional/modern/clean]. Use consistent colors."
```

## Add data loading
```bash
claude "Read .forge/spec.md. Load data from [CSV file / API endpoint]. Handle loading states and errors."
```

## Make it responsive
```bash
claude "Read .forge/spec.md. Make the dashboard responsive so charts resize properly on mobile."
```

---

## For Cursor

1. Open `.forge/spec.md`
2. Press `Cmd+K` (or `Ctrl+K`)
3. Type: "Build this dashboard following rules.md"

---

## For Aider

```bash
aider --read .forge/spec.md --read .forge/rules.md
# Then type: Build this dashboard step by step
```

---

## Running Your Dashboard

### Streamlit
```bash
pip install -r requirements.txt
streamlit run app.py
```

### React
```bash
cd frontend && npm install && npm run dev
```

---

## Tips

- **Start with sample data**: Create a small CSV to test with
- **One chart at a time**: Get each visualization working before adding more
- **Check mobile**: Test how charts look on small screens
- **Keep it simple**: Don't overcrowd with too many metrics
