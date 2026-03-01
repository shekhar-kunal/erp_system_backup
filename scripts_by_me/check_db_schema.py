# check_db_schema.py
import os
import sys
import django

# Add the project directory to the Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_dir)

# Set the Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_system.settings')

# Setup Django
django.setup()

from django.db import connection
from django.apps import apps
from django.db.migrations.executor import MigrationExecutor

def check_db_schema():
    """Compare Django models with actual database schema"""
    
    print("=" * 80)
    print("🔍 CHECKING DATABASE SCHEMA VS MODELS")
    print("=" * 80)
    
    all_models = apps.get_models()
    
    # Check database connection
    try:
        connection.ensure_connection()
        print(f"✅ Connected to database: {connection.vendor}")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    with connection.cursor() as cursor:
        for model in all_models:
            table_name = model._meta.db_table
            
            # Check if table exists (works for SQLite, PostgreSQL, MySQL)
            if connection.vendor == 'sqlite':
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=%s
                """, [table_name])
            elif connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE tablename = %s
                """, [table_name])
            elif connection.vendor == 'mysql':
                cursor.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_name = %s
                """, [table_name])
            
            if not cursor.fetchone():
                print(f"⚠️  Table '{table_name}' doesn't exist for model {model.__name__} (run migrations)")
                continue
            
            # Get columns from database
            if connection.vendor == 'sqlite':
                cursor.execute(f"PRAGMA table_info({table_name})")
                db_columns = [row[1] for row in cursor.fetchall()]
            else:
                # For PostgreSQL/MySQL you'd need different queries
                print(f"  📊 Table {table_name} exists")
                continue
            
            # Get model fields
            model_fields = [field.column for field in model._meta.fields]
            
            # Compare
            missing_in_db = set(model_fields) - set(db_columns)
            extra_in_db = set(db_columns) - set(model_fields) - {'id'}
            
            if missing_in_db:
                print(f"  ⚠️  {model.__name__}: Missing in DB: {missing_in_db}")
            
            if extra_in_db:
                print(f"  ℹ️  {model.__name__}: Extra in DB: {extra_in_db}")
            
            if not missing_in_db and not extra_in_db:
                print(f"  ✅ {model.__name__}: Schema matches")

def check_pending_migrations():
    """Check for pending migrations"""
    print("\n" + "=" * 80)
    print("🔍 CHECKING PENDING MIGRATIONS")
    print("=" * 80)
    
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    
    if plan:
        print(f"⚠️  Pending migrations: {len(plan)}")
        for migration, _ in plan:
            print(f"  - {migration.app_label}: {migration.name}")
    else:
        print("✅ No pending migrations")

if __name__ == "__main__":
    print(f"Using settings module: {os.environ.get('DJANGO_SETTINGS_MODULE')}")
    check_db_schema()
    check_pending_migrations()