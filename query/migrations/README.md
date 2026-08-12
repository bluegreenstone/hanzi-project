# Query schema migrations

The query database uses integer schema versions encoded as `major * 10000 +
minor * 100 + patch`. Migration `0001_initial.sql` creates schema version
`1.0.0` (`PRAGMA user_version = 10000`).

Migrations are append-only after a public release. A builder must apply every
migration in filename order to a new database. Future in-place upgrade tooling
may apply only versions newer than the database's current `user_version`.

Compatibility policy:

- patch releases may add indexes or correct metadata without changing query
  results;
- minor releases may add nullable columns, tables, or views;
- major releases may rename or remove columns, change keys, or alter field
  semantics.

The canonical per-record JSON remains versioned independently by the JSON
Schemas in `schema/`. The query database is a derived access layer and can
always be rebuilt from those records.
