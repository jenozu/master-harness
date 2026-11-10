---
paths:
  - "frontend/**/*.{js,jsx,ts,tsx,css,html}"
  - "frontend/vite.config.*"
---

# React + Vite + Tailwind rules

<!-- Library rule. Adjust the paths above to where the frontend lives in this project. -->

- Function components and hooks only. Keep state local; lift it only when two components need it.
- All API calls go through one client module (e.g. `src/services/api.js`); base URL from `VITE_API_URL`.
  Encode query params; cancel stale requests (AbortController) for search-as-you-type.
- Tailwind utility classes; shared values (colors, spacing) in the Tailwind config or one theme file.
  No new UI or state library without a PRD decision.
- Every data view has loading, empty and error states.
- Accessibility: real buttons and labels, alt text, focus visible, color contrast.
- Before reporting done: `npm run build` passes and lint is clean for the files you touched
  (`npx eslint <files>` if the repo-wide lint has old failures).
