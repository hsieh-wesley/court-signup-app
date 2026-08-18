from django.db import migrations


def backfill(apps, schema_editor):
    Location = apps.get_model("courts", "Location")
    Court = apps.get_model("courts", "Court")

    courts = list(Court.objects.filter(location__isnull=True).order_by("id"))
    if not courts:
        return

    location, _ = Location.objects.get_or_create(name="Test Location")
    for number, court in enumerate(courts, start=1):
        court.location = location
        court.number = number
        if not court.name or court.name.strip() == "":
            court.name = f"Court {number}"
        court.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("courts", "0004_location_court_number_alter_court_name_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
