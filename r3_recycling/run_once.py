import os

# Solo ejecutar si no hay migraciones previas hechas
if not os.path.exists('migrated.flag'):
    os.system('python manage.py migrate')
    os.system('python manage.py collectstatic --noinput')

    # Crear un archivo de bandera para no repetir
    with open('migrated.flag', 'w') as f:
        f.write('done')