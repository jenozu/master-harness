---
name: db-migration
description: Create, review and test a database migration safely. Use whenever a task changes a data model, a table or a column (Alembic, Prisma, Drizzle, Django, Knex or plain SQL migrations).
---

# Database migration procedure

<!-- Library skill. BOOTSTRAP keeps only the section for this project's migration tool and fills in the paths. -->

## Always
1. **Change the model first**, then generate the migration. New columns on tables with data: nullable or with a
   default, so the upgrade works on existing rows. Keep old columns that existing rows still use.
2. **Read the generated migration.** Autogenerate gets these wrong; fix by hand:
   - renames detected as drop + add (loses data) → use a real rename;
   - NOT NULL added to a populated table → default or backfill step first;
   - tables owned by something else (raw SQL schema files, another service) must not appear.
   - The down/rollback must really undo the up.
3. **Round trip on a dev database that has data:** up → down → up. Then the tool's "no pending changes" check.
4. **Run the test suite** against the test database.
5. Commit the migration together with the model change. A destructive migration (drops, type changes) also gets
   `review: true` on its task and a backup step in the deploy instructions.

## Tool commands
- **Alembic:** `alembic revision --autogenerate -m "<what>"` · `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` · `alembic check`
- **Prisma:** `npx prisma migrate dev --name <what>` · reset only the dev db: `npx prisma migrate reset` · `npx prisma migrate status`
- **Drizzle:** `npx drizzle-kit generate` · `npx drizzle-kit migrate` · inspect the SQL in the migrations folder
- **Django:** `python manage.py makemigrations` · `python manage.py migrate` · `python manage.py migrate <app> <previous>` · `python manage.py makemigrations --check`
- **Knex:** `npx knex migrate:make <what>` · `npx knex migrate:latest && npx knex migrate:rollback && npx knex migrate:latest`
