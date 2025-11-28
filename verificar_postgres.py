#!/usr/bin/env python
"""Script para verificar que PostgreSQL está configurado correctamente"""
import os
import sys

# Asegurar que usa settings.local
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.local')

import django
django.setup()

from django.conf import settings
from django.db import connection

print("=" * 60)
print("VERIFICACIÓN DE BASE DE DATOS")
print("=" * 60)

# Verificar configuración
db_config = settings.DATABASES['default']
print(f"\n📊 Configuración de Base de Datos:")
print(f"   Engine: {db_config['ENGINE']}")
print(f"   Name: {db_config['NAME']}")
print(f"   User: {db_config['USER']}")
print(f"   Host: {db_config['HOST']}")
print(f"   Port: {db_config['PORT']}")

# Verificar conexión
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"\n✅ Conexión exitosa a PostgreSQL!")
        print(f"   Versión: {version[:80]}...")
        
        # Verificar que no sea SQLite
        if 'sqlite' in db_config['ENGINE'].lower():
            print("\n❌ ERROR: Estás usando SQLite en lugar de PostgreSQL!")
            print("   Esto causará lentitud en eliminaciones masivas.")
            sys.exit(1)
        else:
            print("\n✅ Usando PostgreSQL correctamente")
            
except Exception as e:
    print(f"\n❌ ERROR al conectar a la base de datos:")
    print(f"   {str(e)}")
    print("\n💡 Verifica que:")
    print("   1. PostgreSQL esté corriendo")
    print("   2. Las credenciales en .env sean correctas")
    print("   3. La base de datos exista")
    sys.exit(1)

print("\n" + "=" * 60)

