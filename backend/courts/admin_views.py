from django.db.models import Max, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import admin_services, services
from .admin_serializers import (
    AdminAddLoginSerializer,
    AdminBulkTestPlayersSerializer,
    AdminCourtCountSerializer,
    AdminCourtCreateSerializer,
    AdminCourtSerializer,
    AdminLocationCreateSerializer,
    AdminLocationEditSerializer,
    AdminLocationSerializer,
    AdminMembershipCreateSerializer,
    AdminMembershipEditSerializer,
    AdminMembershipSerializer,
    AdminPlayerCreateSerializer,
    AdminPlayerEditSerializer,
    AdminPlayerSerializer,
    AdminRemovePlayerSerializer,
    CourtActivityLogSerializer,
    LoginLogSerializer,
)
from .models import Court, CourtActivityLog, Location, LoginLog, Pair, Player, QueueEntry
from .permissions import IsAdmin, IsSuperUser


def _get_player_or_404(pk):
    try:
        return Player.objects.get(pk=pk)
    except Player.DoesNotExist:
        return None


def _get_court_or_404(pk):
    try:
        return Court.objects.get(pk=pk)
    except Court.DoesNotExist:
        return None


def _get_location_or_404(pk):
    try:
        return Location.objects.get(pk=pk)
    except Location.DoesNotExist:
        return None


def _assignment_map():
    """{user_id: {"status": "active"|"waiting", "court_number": N}} for every
    player currently on a court/queue anywhere — global, not location-
    filtered, since a player can only be active/waiting at one facility at
    a time (services._reject_if_active_elsewhere)."""
    pairs = Pair.objects.filter(
        entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
    ).select_related("entry__court")
    result = {}
    for pair in pairs:
        info = {"status": pair.entry.status, "court_number": pair.entry.court.number}
        result[pair.player_1_id] = info
        result[pair.player_2_id] = info
    return result


def _checkin_map(location_id):
    """{user_id: latest registration/check-in datetime today} for one
    location. Empty if no location_id was given."""
    if not location_id:
        return {}
    rows = (
        LoginLog.objects.filter(
            location_id=location_id,
            context__in=[
                LoginLog.Context.REGISTRATION,
                LoginLog.Context.CHECK_IN,
                LoginLog.Context.MEMBER_CHECK_IN,
            ],
            created_at__date=timezone.localdate(),
        )
        .values("user_id")
        .annotate(latest=Max("created_at"))
    )
    return {row["user_id"]: row["latest"] for row in rows}


def _location_counts():
    """{location_id: {"waiting_room", "in_queue", "on_court"}} for every
    location. on_court/in_queue come straight from today's Pair rows;
    waiting_room is today's distinct checked-in users at that location,
    minus whoever is currently assigned anywhere (same invariant as
    _assignment_map — presence and assignment are mutually exclusive)."""
    counts = {
        loc_id: {"waiting_room": 0, "in_queue": 0, "on_court": 0}
        for loc_id in Location.objects.values_list("id", flat=True)
    }

    pairs = Pair.objects.filter(
        entry__status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
    ).select_related("entry__court")
    assigned_user_ids = set()
    for pair in pairs:
        key = "on_court" if pair.entry.status == QueueEntry.Status.ACTIVE else "in_queue"
        counts[pair.entry.court.location_id][key] += 2
        assigned_user_ids.add(pair.player_1_id)
        assigned_user_ids.add(pair.player_2_id)

    checkins = (
        LoginLog.objects.filter(
            context__in=[
                LoginLog.Context.REGISTRATION,
                LoginLog.Context.CHECK_IN,
                LoginLog.Context.MEMBER_CHECK_IN,
            ],
            created_at__date=timezone.localdate(),
            location_id__isnull=False,
        )
        .values("location_id", "user_id")
        .distinct()
    )
    for row in checkins:
        if row["user_id"] in assigned_user_ids:
            continue
        counts[row["location_id"]]["waiting_room"] += 1

    return counts


class AdminPlayerListCreateView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        players = Player.objects.select_related("user").order_by("display_name")
        location_id = request.query_params.get("location_id")
        context = {"assignments": _assignment_map(), "checkins": _checkin_map(location_id)}
        return Response(AdminPlayerSerializer(players, many=True, context=context).data)

    def post(self, request):
        serializer = AdminPlayerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            player, _ = admin_services.create_player(
                display_name=data["display_name"],
                username=data.get("username") or None,
                enable_login=data.get("enable_login", False),
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminPlayerSerializer(player).data, status=status.HTTP_201_CREATED)


class AdminPlayerDetailView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminPlayerEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            player = admin_services.edit_player(player, **serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminPlayerSerializer(player).data)


class AdminPlayerLoginView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminAddLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plaintext = admin_services.add_login(player, serializer.validated_data["username"])
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        payload = AdminPlayerSerializer(player).data
        payload["password"] = plaintext
        return Response(payload)


class AdminPlayerDisableLoginView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            admin_services.disable_login(player)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminPlayerSerializer(player).data)


class AdminPlayerResetPasswordView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            plaintext = admin_services.reset_password(player)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        payload = AdminPlayerSerializer(player).data
        payload["password"] = plaintext
        return Response(payload)


class AdminPlayerDeactivateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.deactivate_player(player, actor=request.user)
        return Response(AdminPlayerSerializer(player).data)


class AdminBulkTestPlayersView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = AdminBulkTestPlayersSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = admin_services.create_test_players(serializer.validated_data["count"])
        return Response(results, status=status.HTTP_201_CREATED)


class AdminCourtCreateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = AdminCourtCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            court = admin_services.create_court(
                location=data["location_id"],
                number=data.get("number"),
                capacity=data.get("capacity"),
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminCourtSerializer(court).data, status=status.HTTP_201_CREATED)


class AdminCourtRemovePlayerView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminRemovePlayerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            admin_services.remove_player_from_court(
                court, serializer.validated_data["username"], actor=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCourtDropView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.drop_court(court, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCourtDeactivateView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        court = _get_court_or_404(pk)
        if court is None:
            return Response({"detail": "Court not found."}, status=status.HTTP_404_NOT_FOUND)
        admin_services.deactivate_court(court, actor=request.user)
        return Response(AdminCourtSerializer(court).data)


class AdminLocationListCreateView(APIView):
    """GET is available to staff and admin alike; POST (creating a
    brand-new facility) is admin/superuser-only."""

    permission_classes = [IsAdmin]

    def get(self, request):
        locations = Location.objects.all().order_by("name")
        context = {"location_counts": _location_counts()}
        return Response(AdminLocationSerializer(locations, many=True, context=context).data)

    def post(self, request):
        if not request.user.is_superuser:
            return Response(
                {"detail": "This action requires the admin account."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AdminLocationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            location = admin_services.create_location(**serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminLocationSerializer(location).data, status=status.HTTP_201_CREATED)


class AdminLocationDetailView(APIView):
    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        location = _get_location_or_404(pk)
        if location is None:
            return Response({"detail": "Location not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminLocationEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            location = admin_services.edit_location(location, **serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminLocationSerializer(location).data)


class AdminLocationDeleteView(APIView):
    """Admin/superuser-only, matching create. Permanently deletes only if
    admin_services.delete_location finds zero history; otherwise responds
    with the same explanation the location's has_history field predicts,
    so admin knows to deactivate instead."""

    permission_classes = [IsSuperUser]

    def post(self, request, pk):
        location = _get_location_or_404(pk)
        if location is None:
            return Response({"detail": "Location not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            admin_services.delete_location(location)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminLocationCourtCountView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        location = _get_location_or_404(pk)
        if location is None:
            return Response({"detail": "Location not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminCourtCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            admin_services.set_court_count(
                location, serializer.validated_data["count"], actor=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminLocationSerializer(location).data)


class AdminStaffResetPasswordView(APIView):
    """Admin/superuser-only — staff cannot reset its own password. In
    place, no account recreation; invalidates any existing staff session."""

    permission_classes = [IsSuperUser]

    def post(self, request):
        try:
            plaintext = admin_services.reset_staff_password()
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response({"password": plaintext})


class AdminMembershipListCreateView(APIView):
    """POST also renews a lapsed member: pass their existing username and
    admin_services.start_membership reuses that Player/User rather than
    creating a duplicate account."""

    permission_classes = [IsAdmin]

    def get(self, request):
        players = (
            Player.objects.filter(memberships__isnull=False)
            .distinct()
            .select_related("user")
            .order_by("display_name")
        )
        return Response(AdminMembershipSerializer(players, many=True).data)

    def post(self, request):
        serializer = AdminMembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            player, _membership, plaintext = admin_services.start_membership(
                username=data["username"],
                phone_number=data["phone_number"],
                expires_at=data.get("expires_at"),
                location=data.get("location"),
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        payload = AdminMembershipSerializer(player).data
        if plaintext:
            payload["password"] = plaintext
        return Response(payload, status=status.HTTP_201_CREATED)


class AdminMembershipDetailView(APIView):
    """PATCH edits the player's CURRENT (not-yet-lapsed) membership row —
    phone number and/or expiration. 404s if they have no membership at
    all; rejects editing an already-lapsed row (see admin_services.
    update_membership) — renew via AdminMembershipListCreateView.post
    instead, which starts a fresh period."""

    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        player = _get_player_or_404(pk)
        if player is None:
            return Response({"detail": "Player not found."}, status=status.HTTP_404_NOT_FOUND)
        membership = player.memberships.order_by("-starts_at").first()
        if membership is None:
            return Response({"detail": "This player has no membership."}, status=status.HTTP_404_NOT_FOUND)
        serializer = AdminMembershipEditSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            admin_services.update_membership(membership, **serializer.validated_data)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(AdminMembershipSerializer(player).data)


class AdminLoginHistoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = LoginLog.objects.select_related("user", "location").all()
        location_id = request.query_params.get("location_id")
        if location_id:
            qs = qs.filter(location_id=location_id)
        username = request.query_params.get("username")
        if username:
            qs = qs.filter(username=username)
        context = request.query_params.get("context")
        if context:
            qs = qs.filter(context=context)
        membership = request.query_params.get("membership")
        if membership:
            qs = qs.filter(membership_status=membership)
        date = request.query_params.get("date")
        if date:
            qs = qs.filter(created_at__date=date)
        limit = int(request.query_params.get("limit", 200))
        return Response(LoginLogSerializer(qs[:limit], many=True).data)


class AdminCourtActivityHistoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        qs = CourtActivityLog.objects.all()
        location_id = request.query_params.get("location_id")
        if location_id:
            qs = qs.filter(location_id=location_id)
        court_id = request.query_params.get("court_id")
        if court_id:
            qs = qs.filter(court_id=court_id)
        event_type = request.query_params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)
        username = request.query_params.get("username")
        if username:
            qs = qs.filter(Q(player_1_username=username) | Q(player_2_username=username))
        membership = request.query_params.get("membership")
        if membership == "member":
            qs = qs.filter(
                Q(player_1_membership_status="member") | Q(player_2_membership_status="member")
            )
        elif membership == "non_member":
            qs = qs.filter(
                Q(player_1_membership_status="non_member")
                | Q(player_2_membership_status="non_member")
            ).exclude(
                Q(player_1_membership_status="member") | Q(player_2_membership_status="member")
            )
        date = request.query_params.get("date")
        if date:
            qs = qs.filter(created_at__date=date)
        limit = int(request.query_params.get("limit", 200))
        return Response(CourtActivityLogSerializer(qs[:limit], many=True).data)
