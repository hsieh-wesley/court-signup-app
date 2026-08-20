from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

DEFAULT_STAFF_PASSWORD = "staffpass123"


class Command(BaseCommand):
    help = (
        "Idempotently create the 'staff' admin-tier account (is_staff=True, "
        "is_superuser=False) with a default password. Does NOT touch the "
        "password if the account already exists -- use the admin interface's "
        "Reset Staff Password action to change it afterward, not a re-run "
        "of this command."
    )

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username="staff", defaults={"is_staff": True, "is_superuser": False}
        )
        if created:
            user.set_password(DEFAULT_STAFF_PASSWORD)
            user.is_staff = True
            user.is_superuser = False
            user.save()
            self.stdout.write(f"staff: created with password {DEFAULT_STAFF_PASSWORD}")
        else:
            self.stdout.write("staff: already exists, password left untouched")
