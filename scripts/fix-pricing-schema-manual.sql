-- Emergency fix if admin Service rates save fails (missing wa_survey_extra_pence).
-- Safe to run multiple times — skips if column already exists.

SET @db := DATABASE();

SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE pricing_global_settings ADD COLUMN wa_survey_extra_pence INT NOT NULL DEFAULT 49',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db
    AND TABLE_NAME = 'pricing_global_settings'
    AND COLUMN_NAME = 'wa_survey_extra_pence'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE org_custom_pricing ADD COLUMN wa_survey_extra_pence INT NULL',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db
    AND TABLE_NAME = 'org_custom_pricing'
    AND COLUMN_NAME = 'wa_survey_extra_pence'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
