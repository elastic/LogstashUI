-- Empty PostgreSQL 14+ database for LogstashUI.
-- Tables are created by: logstashui manage migrate --noinput
-- Replace the password before running.

CREATE USER logstashui WITH LOGIN PASSWORD 'change-me';
CREATE DATABASE logstashui
  OWNER logstashui
  ENCODING 'UTF8'
  TEMPLATE template0;

\connect logstashui
GRANT ALL ON SCHEMA public TO logstashui;
ALTER DATABASE logstashui OWNER TO logstashui;
