from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            """
            CREATE SCHEMA IF NOT EXISTS collection;
            CREATE SCHEMA IF NOT EXISTS dictionary;
            CREATE SCHEMA IF NOT EXISTS commerce;
            CREATE SCHEMA IF NOT EXISTS content;
            CREATE SCHEMA IF NOT EXISTS snapshot;
            CREATE SCHEMA IF NOT EXISTS analysis;
            CREATE SCHEMA IF NOT EXISTS app;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]