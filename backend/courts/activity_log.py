from .membership import membership_status_for
from .models import CourtActivityLog, LoginLog


def log_player_auth_event(user, location, context):
    LoginLog.objects.create(
        user=user,
        username=user.username,
        location=location,
        location_name=location.name if location else "",
        context=context,
        membership_status=membership_status_for(user),
    )


def log_pair_event(event_type, court, entry, pair, reason="", actor=None):
    CourtActivityLog.objects.create(
        event_type=event_type,
        reason=reason,
        location=court.location,
        location_name=court.location.name,
        court=court,
        court_number=court.number,
        entry=entry,
        pair=pair,
        player_1_username=pair.player_1.username,
        player_2_username=pair.player_2.username,
        player_1_membership_status=membership_status_for(pair.player_1),
        player_2_membership_status=membership_status_for(pair.player_2),
        actor_username=actor.username if actor else "",
    )


def log_court_event(event_type, court, actor=None):
    CourtActivityLog.objects.create(
        event_type=event_type,
        location=court.location,
        location_name=court.location.name,
        court=court,
        court_number=court.number,
        actor_username=actor.username if actor else "",
    )
