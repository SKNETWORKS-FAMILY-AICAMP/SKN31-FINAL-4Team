from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0067_notification_ops_alert"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE "analysis"."text_term_mention"
                        DROP COLUMN IF EXISTS "analysis_version";

                        ALTER TABLE "analysis"."text_term_mention"
                        DROP COLUMN IF EXISTS "evidence_start";

                        ALTER TABLE "analysis"."text_term_mention"
                        DROP COLUMN IF EXISTS "evidence_end";

                        ALTER TABLE "analysis"."text_term_mention"
                        DROP COLUMN IF EXISTS "evidence_status";
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="texttermmention",
                    name="analysis_version",
                ),
                migrations.RemoveField(
                    model_name="texttermmention",
                    name="evidence_start",
                ),
                migrations.RemoveField(
                    model_name="texttermmention",
                    name="evidence_end",
                ),
                migrations.RemoveField(
                    model_name="texttermmention",
                    name="evidence_status",
                ),
            ],
        ),
    ]