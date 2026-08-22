from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0015_pushtoken"),
    ]

    operations = [
        migrations.CreateModel(
            name="Client",
            fields=[],
            options={
                "verbose_name": "Client",
                "verbose_name_plural": "Clients",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("users.profile",),
        ),
        migrations.CreateModel(
            name="Performer",
            fields=[],
            options={
                "verbose_name": "Performer",
                "verbose_name_plural": "Performers",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("users.profile",),
        ),
    ]
