-- Empty MySQL 8.0+ database for LogstashUI.
-- utf8mb4_bin keeps unique names case-sensitive like SQLite/Postgres.
-- Tables are created by: logstashui manage migrate --noinput
-- Replace the password before running.

CREATE DATABASE IF NOT EXISTS logstashui
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_bin;

CREATE USER IF NOT EXISTS 'logstashui'@'%' IDENTIFIED BY 'change-me';
GRANT ALL PRIVILEGES ON logstashui.* TO 'logstashui'@'%';
FLUSH PRIVILEGES;
