---
paths:
  - "**/*.ts"
  - "**/*.tsx"
---

# Node + TypeScript rules

<!-- Library rule. Adjust the paths above if the TypeScript code lives in specific folders. -->

- `strict` TypeScript. No `any` in new code; use `unknown` and narrow. No `// @ts-ignore` without a comment why.
- Validate external input at the boundary (zod or the project's chosen validator), then trust the types inside.
- Use the package manager the repo already uses (lockfile tells you: npm, pnpm, yarn, bun). Never mix them.
- Async: always await or return promises; no floating promises. Handle errors where you can act on them.
- Config from environment variables, read and validated in one module.
- Tests with the project's runner (vitest/jest/node:test). Run `tsc --noEmit` and the tests before reporting done.
