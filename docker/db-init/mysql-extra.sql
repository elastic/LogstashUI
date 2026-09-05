CREATE DATABASE IF NOT EXISTS logstashui_migrate CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
GRANT ALL ON logstashui_migrate.* TO 'logstashui'@'%';
GRANT ALL ON logstashui_migrate.* TO 'root'@'%';
