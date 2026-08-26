import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from courts.models import StaffCredential
from courts.password_gen import generate_admin_password

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Idempotently create the 'staff' admin-tier account (is_staff=True, "
        "is_superuser=False). No hardcoded password: uses SEED_STAFF_PASSWORD "
        "from the environment if set (handy for reproducible local/CI runs), "
        "otherwise generates a fresh cryptographically random one and prints "
        "it once -- it is never logged or stored anywhere else in plaintext "
        "except StaffCredential (viewable again later via the admin UI's "
        "Reset Staff Password action). Does NOT touch the password if the "
        "account already exists -- use that Reset Staff Password action to "
        "change it afterward, not a re-run of this command."
    )

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username="staff", defaults={"is_staff": True, "is_superuser": False}
        )
        if created:
            plaintext = os.environ.get("SEED_STAFF_PASSWORD") or generate_admin_password()
            user.set_password(plaintext)
            user.is_staff = True
            user.is_superuser = False
            user.save()
            StaffCredential.objects.update_or_create(
                user=user, defaults={"current_password_plaintext": plaintext}
            )
            self.stdout.write(f"staff: created with password {plaintext}")
        else:
            self.stdout.write("staff: already exists, password left untouched")
