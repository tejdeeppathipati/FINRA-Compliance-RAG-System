# Frontend

Small React + TypeScript evidence viewer for the FastAPI backend. It supports a question,
retrieval-mode selection, citations, expandable retrieved passages, source links, and the
explicit abstention state.

```bash
npm install
npm run dev
```

Vite proxies `/api` requests to `http://localhost:8000`. The evaluation-results view is
intentionally deferred until the evaluation runner has real saved results to display.
