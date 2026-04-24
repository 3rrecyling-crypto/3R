# Manually patched: conversión de RH_empleado.id INTEGER -> UUID
# El ALTER auto-generado por Django usa "USING id::uuid" que PostgreSQL rechaza.
# Esta migración usa RunSQL con USING gen_random_uuid() y aborta si la tabla tiene datos
# para evitar pérdida silenciosa (requeriría migración manual en ese caso).

import django.utils.timezone
import uuid
from django.db import migrations, models


CONVERT_SQL = r"""
-- Extensión necesaria para gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Tabla temporal para recordar las FKs que se van a recrear
CREATE TEMP TABLE _rh_fks_backup (
    table_schema text,
    table_name   text,
    column_name  text,
    constraint_name text
) ON COMMIT DROP;

DO $$
DECLARE
    row_count bigint;
    r record;
BEGIN
    -- Abortar si la tabla tiene datos: la conversión INTEGER->UUID pierde los IDs
    SELECT COUNT(*) INTO row_count FROM "RH_empleado";
    IF row_count > 0 THEN
        RAISE EXCEPTION 'RH_empleado tiene % filas — la conversión de INTEGER a UUID requiere migración manual. Vacía la tabla o escribe una migración personalizada.', row_count;
    END IF;

    -- 1) Guardar y quitar todas las FK que referencian RH_empleado.id, luego convertir a uuid
    FOR r IN
        SELECT
            tc.table_schema,
            tc.table_name,
            tc.constraint_name,
            kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema   = kcu.table_schema
        JOIN information_schema.referential_constraints rc
            ON rc.constraint_name = tc.constraint_name
           AND rc.constraint_schema = tc.table_schema
        JOIN information_schema.key_column_usage pku
            ON pku.constraint_name = rc.unique_constraint_name
           AND pku.constraint_schema = rc.unique_constraint_schema
        WHERE pku.table_name = 'RH_empleado'
          AND pku.column_name = 'id'
          AND tc.constraint_type = 'FOREIGN KEY'
    LOOP
        INSERT INTO _rh_fks_backup VALUES (r.table_schema, r.table_name, r.column_name, r.constraint_name);
        EXECUTE format('ALTER TABLE %I.%I DROP CONSTRAINT %I',
                       r.table_schema, r.table_name, r.constraint_name);
        EXECUTE format('ALTER TABLE %I.%I ALTER COLUMN %I DROP DEFAULT',
                       r.table_schema, r.table_name, r.column_name);
        EXECUTE format('ALTER TABLE %I.%I ALTER COLUMN %I TYPE uuid USING NULL',
                       r.table_schema, r.table_name, r.column_name);
    END LOOP;

    -- 2) Convertir RH_empleado.id de integer a uuid (tabla vacía -> gen_random_uuid() es seguro)
    ALTER TABLE "RH_empleado" ALTER COLUMN "id" DROP DEFAULT;
    ALTER TABLE "RH_empleado" ALTER COLUMN "id" TYPE uuid USING gen_random_uuid();
    ALTER TABLE "RH_empleado" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

    -- 3) Recrear las FKs ahora que ambos lados son uuid
    FOR r IN SELECT * FROM _rh_fks_backup
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I (%I) DEFERRABLE INITIALLY DEFERRED',
            r.table_schema, r.table_name, r.constraint_name,
            r.column_name, 'RH_empleado', 'id'
        );
    END LOOP;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("RH", "0002_empleado_origen_id_and_more"),
    ]

    operations = [
        # Cambios que no afectan la PK
        migrations.AlterField(
            model_name="empleado",
            name="fecha_contratacion",
            field=models.DateField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="empleado",
            name="numero_empleado",
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
        # Conversión INTEGER->UUID mediante SQL explícito.
        # El AlterField de id va en state_operations para que Django actualice su estado
        # sin intentar generar el ALTER que falla.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="empleado",
                    name="id",
                    field=models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=CONVERT_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
