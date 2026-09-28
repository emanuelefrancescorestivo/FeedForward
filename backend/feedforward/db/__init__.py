"""
Persistence for FeedForward.

The scientific engine stays free of SQL. This package is the storage adapter:
users, and the food/nutrient/goal corpus the engine used to parse from JSON.

Production dialect is PostgreSQL (see docker-compose.yml and Alembic). The
models use portable column types so the same repository can be exercised on
SQLite in tests and on a machine that does not have a Postgres server. SQLite
is a test/dev double, not a second product database.
"""
