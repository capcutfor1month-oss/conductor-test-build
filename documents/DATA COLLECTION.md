# Data Collection

---

## Goal

Collect anonymous user pattern data to improve Conductor's routing, stage detection, and responses over time. More data = smarter Auto mode for every user.

---

## What to Collect

Not chat content. Only patterns:

| Data Point | Why |
|---|---|
| Stage at time of question | Improves stage detection |
| Source routed (NLM / Ableton / Memory / Direct) | Improves Semantic Router |
| Did user follow up or correct the answer | Measures answer quality |
| Session length per sitting | Understands usage depth |
| Track count at each stage | Improves stage inference |
| Question category (EQ / arrangement / theory / etc.) | Improves routing priority |
| Error patterns from errors.md (task + failure type) | Improves ableton.md known failure patterns |
| How many attempts before task succeeded | Measures AI reliability per task type |

---

## What NOT to Collect

- Chat content
- Project names
- File paths
- Plugin names
- Any personally identifiable information

---

## How It Works

```
User interaction happens locally
     ↓
ChromaDB stores pattern locally
     ↓
If user opted in → anonymous pattern sent to Conductor server
     ↓
Server aggregates patterns across all users
     ↓
Improvements pushed back via update pipeline
```

---

## User Consent

- Opt-in only. Never on by default.
- Toggle in Settings: "Help improve Conductor by sharing anonymous usage data"
- User can turn off anytime
- Data is anonymised before leaving the machine

---

## What Needs to Be Built

- Opt-in toggle in Settings UI
- Anonymisation layer before sending
- POST endpoint on Conductor server to receive data
- Database schema for storing aggregated patterns
- Privacy policy

---

## Future Use

- Train Semantic Router on real routing decisions across all users
- Improve stage inference thresholds
- Surface common patterns back as smart suggestions in Conductor

---

## Status

Not built. Planned for post-launch.
