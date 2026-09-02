# Database examples

Apply a **create-*.sql** script to an empty server, then start LogstashUI (`migrate` creates tables).

| File | Use |
|---|---|
| [create-postgresql.sql](create-postgresql.sql) | Role + database (UTF8) |
| [create-mysql.sql](create-mysql.sql) | MySQL 8.0+ `utf8mb4` / `utf8mb4_bin` |
| [create-mariadb.sql](create-mariadb.sql) | MariaDB 10.6+ same collation |
| [schema-postgresql.sql](schema-postgresql.sql) | Snapshot of `migrate` DDL (reference) |
| [schema-mysql.sql](schema-mysql.sql) | Snapshot of `migrate` DDL (reference) |

`schema-*.sql` is generated from LogstashUI **0.5.2** migrations. It **will go stale**. Do not apply it instead of `logstashui manage migrate --noinput`. It exists so you can see tables, indexes, and the MySQL collation before you run migrate.

CloudNativePG: bootstrap `database` / `owner` already creates the empty database — skip `create-postgresql.sql`, still run migrate.
