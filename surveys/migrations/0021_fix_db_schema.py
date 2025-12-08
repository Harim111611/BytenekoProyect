# surveys/migrations/0021_fix_db_schema.py

from django.db import migrations, connection

def fix_columns(apps, schema_editor):
    with connection.cursor() as cursor:
        # 1. Verificar qué columnas existen realmente
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'surveys_question'
        """)
        columns = [row[0] for row in cursor.fetchall()]
        
        # Escenario: Existen AMBAS columnas ('type' y 'column_type')
        if 'type' in columns and 'column_type' in columns:
            print("\nDetectado conflicto de columnas. Sincronizando datos...")
            # Copiar datos de la vieja a la nueva por si acaso
            cursor.execute("""
                UPDATE surveys_question 
                SET column_type = type 
                WHERE column_type IS NULL AND type IS NOT NULL
            """)
            # Eliminar la columna vieja que causa el error NOT NULL
            print("Eliminando columna obsoleta 'type'...")
            cursor.execute('ALTER TABLE surveys_question DROP COLUMN "type"')
            
        # Escenario: Solo existe 'type' pero Django espera 'column_type'
        # (Esto pasa si el --fake se hizo antes de que existiera la columna real)
        elif 'type' in columns and 'column_type' not in columns:
            print("\nRenombrando columna 'type' a 'column_type'...")
            cursor.execute('ALTER TABLE surveys_question RENAME COLUMN "type" TO "column_type"')

class Migration(migrations.Migration):

    dependencies = [
        # Asegúrate de que esta dependencia coincida con tu último archivo existente
        ('surveys', '0020_alter_question_type'),
    ]

    operations = [
        migrations.RunPython(fix_columns),
    ]