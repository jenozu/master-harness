---
paths:
  - "**/*.sql"
  - "**/migrations/**"
  - "**/alembic/**"
  - "**/prisma/**"
---

# Postgres rules

<!-- Library rule. -->

- Schema changes only through the project's migration tool (`db-migration` skill). Never edit an applied migration.
- Dev and test databases are separate; tests never touch dev data. Connection strings come from env vars.
- Add indexes for columns used in WHERE/JOIN/ORDER BY on tables that will grow; check with `EXPLAIN ANALYZE` when a
  query matters.
- Bound parameters only. No string-built SQL from user input.
- Destructive statements (`DROP`, `TRUNCATE`, `DELETE` without WHERE) only against local dev/test databases.
- Timestamps as `timestamptz`; money as integer cents or `numeric`, never float.
