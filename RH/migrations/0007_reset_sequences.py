from django.db import migrations

def reset_sequences(apps, schema_editor):
    """
    Resets the sequences for all models in the RH app to avoid IntegrityError (duplicate key)
    This is common when importing data or manual ID assignment.
    """
    from django.db import connection
    from django.core.management.color import no_style
    
    # Get all models for the current app
    app_config = apps.get_app_config('RH')
    models = app_config.get_models()
    
    # Generate the SQL to reset sequences
    sequence_sql = connection.ops.sequence_reset_sql(no_style(), models)
    
    # Execute the SQL
    if sequence_sql:
        with connection.cursor() as cursor:
            for sql in sequence_sql:
                cursor.execute(sql)
                
class Migration(migrations.Migration):
    dependencies = [
        ('RH', '0006_sync_null_constraints'),
    ]

    operations = [
        migrations.RunPython(reset_sequences),
    ]
