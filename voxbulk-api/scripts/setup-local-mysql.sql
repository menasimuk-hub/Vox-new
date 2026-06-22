-- Run in MySQL Workbench while connected as root (local machine only).
-- Creates the same user/database name as production VPS so your DATABASE_URL works locally.

CREATE DATABASE IF NOT EXISTS sql_voxbulk
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Must match the password in voxbulk-api/.env DATABASE_URL
CREATE USER IF NOT EXISTS 'sql_voxbulk'@'localhost' IDENTIFIED BY '6xHrFN7FHr85McFn';
CREATE USER IF NOT EXISTS 'sql_voxbulk'@'127.0.0.1' IDENTIFIED BY '6xHrFN7FHr85McFn';

GRANT ALL PRIVILEGES ON sql_voxbulk.* TO 'sql_voxbulk'@'localhost';
GRANT ALL PRIVILEGES ON sql_voxbulk.* TO 'sql_voxbulk'@'127.0.0.1';

FLUSH PRIVILEGES;

-- Verify (optional):
-- SHOW GRANTS FOR 'sql_voxbulk'@'127.0.0.1';
