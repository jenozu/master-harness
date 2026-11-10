---
paths:
  - "app/**"
  - "src/app/**"
  - "pages/**"
  - "next.config.*"
---

# Next.js rules

<!-- Library rule. Check the paths above match this project's router layout. -->

- App Router conventions: server components by default; add `"use client"` only where state, effects or browser
  APIs are needed, as low in the tree as possible.
- Data fetching and secrets stay on the server (server components, route handlers, server actions). Never import
  server-only modules or env vars without `NEXT_PUBLIC_` into client components.
- Validate every server action and route handler input; check auth inside each one, not only in middleware.
- Use `next/image` and `next/link`. Set metadata per route.
- `npm run build` must pass (it type-checks and lints) before reporting done.
