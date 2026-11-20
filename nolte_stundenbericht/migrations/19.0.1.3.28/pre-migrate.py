"""Preserve existing Community dates before replacing the public field with an alias."""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'project_task'
          AND column_name IN ('nolte_service_date_start', 'nolte_service_date_start_value')
    """)
    columns = {row[0] for row in cr.fetchall()}
    if 'nolte_service_date_start' in columns:
        if 'nolte_service_date_start_value' not in columns:
            cr.execute('ALTER TABLE project_task RENAME COLUMN nolte_service_date_start TO nolte_service_date_start_value')
        else:
            cr.execute("""
                SELECT id FROM project_task WHERE nolte_service_date_start IS NOT NULL
                  AND nolte_service_date_start_value IS NOT NULL
                  AND nolte_service_date_start <> nolte_service_date_start_value LIMIT 1
            """)
            if cr.fetchone():
                raise ValueError('Conflicting legacy service planning dates require review before upgrade')
            cr.execute("""
                UPDATE project_task SET nolte_service_date_start_value = nolte_service_date_start
                WHERE nolte_service_date_start_value IS NULL AND nolte_service_date_start IS NOT NULL
            """)
            cr.execute('ALTER TABLE project_task DROP COLUMN nolte_service_date_start')
