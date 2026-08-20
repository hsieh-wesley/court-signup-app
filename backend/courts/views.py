from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import activity_log, admin_services, services
from .models import Court, Location, LoginLog, QueueEntry
from .serializers import (
    CourtBoardSerializer,
    CreateQueueEntrySerializer,
    JoinOpenSlotSerializer,
    LocationSerializer,
    MemberCheckInSerializer,
    PlayerStatusSerializer,
    QueueEntrySerializer,
    QuickUnsignSerializer,
    UnsignSerializer,
)

User = get_user_model()


class LoginView(APIView):
    """Admin sign-in only. Regular players never call this under the public
    kiosk model — see RegisterPlayerView / QueueEntryCreateView / etc.,
    which verify credentials fresh on every action instead of a session."""

    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        location_id = request.data.get("location_id")

        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        player = getattr(user, "player", None)
        if player is not None and player.is_expired:
            return Response(
                {"detail": "This account has expired."},
                status=status.HTTP_403_FORBIDDEN,
            )

        location = None
        if location_id is not None:
            try:
                location = Location.objects.get(pk=location_id)
            except Location.DoesNotExist:
                return Response({"detail": "Unknown location."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = services.create_player_session(user, location)
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)

        return Response({
            "token": session.key,
            "username": user.username,
            "is_staff": user.is_staff,
            "location_id": location.id if location else None,
            "location_name": location.name if location else None,
        })


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LocationListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        locations = Location.objects.filter(is_active=True).order_by("name")
        return Response(LocationSerializer(locations, many=True).data)


class CheckUsernameView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        username = request.query_params.get("username", "").strip()
        if not username:
            return Response({"available": False})
        try:
            services.validate_new_username(username)
            available = True
        except services.ServiceError:
            available = False
        return Response({"available": available})


class RegisterPlayerView(APIView):
    """Creates a Player account. Never leaves the kiosk signed in — no
    PlayerSession is created. `location_id` is only used to record a
    REGISTRATION history entry (which facility the kiosk was showing at
    creation time); the account itself stays global and usable anywhere."""

    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        location_id = request.data.get("location_id")
        if not username:
            return Response({"detail": "username is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not location_id:
            return Response({"detail": "location_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            location = Location.objects.get(pk=location_id, is_active=True)
        except Location.DoesNotExist:
            return Response(
                {"detail": "Unknown or inactive location."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            player, plaintext = admin_services.create_player(
                display_name=username, username=username, enable_login=True
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)

        activity_log.log_player_auth_event(player.user, location, LoginLog.Context.REGISTRATION)

        return Response(
            {"username": player.user.username, "password": plaintext},
            status=status.HTTP_201_CREATED,
        )


class CourtListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        location_id = request.query_params.get("location_id")
        courts = Court.objects.all()
        if location_id:
            courts = courts.filter(location_id=location_id)
            services.reap_expired_reservations(court_ids=list(courts.values_list("id", flat=True)))
        else:
            services.reap_expired_reservations()
        courts = courts.order_by("number")
        return Response(CourtBoardSerializer(courts, many=True).data)


class PlayerStatusView(APIView):
    """Public kiosk equivalent of a 'my status' page: verify credentials
    fresh (nothing persisted), return that player's current entries.
    `location_id` is optional and only used to record a STATUS_CHECK
    history entry against the facility the kiosk was showing."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PlayerStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = services.verify_credential(data["username"], data["password"])
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)

        activity_log.log_player_auth_event(
            user, data.get("location_id"), LoginLog.Context.STATUS_CHECK
        )

        entries = (
            QueueEntry.objects.filter(
                Q(pairs__player_1=user) | Q(pairs__player_2=user),
                status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
            )
            .distinct()
            .order_by("created_at", "id")
        )
        return Response(QueueEntrySerializer(entries, many=True).data)


class QueueEntryCreateView(APIView):
    """Public kiosk endpoint — no session. Every named player's credentials
    are verified fresh in this one request; there's no 'self' exemption."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CreateQueueEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        court = serializer.validated_data["court_id"]
        try:
            pairs = services.verify_pair_credentials(
                serializer.validated_data["pairs"], court.location
            )
            created_by = User.objects.get(username=pairs[0][0])
            entry = services.create_queue_entry(
                court=court, pairs=pairs, created_by=created_by
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(
            QueueEntrySerializer(entry).data, status=status.HTTP_201_CREATED
        )


class JoinOpenSlotView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, pk):
        try:
            entry = QueueEntry.objects.get(pk=pk)
        except QueueEntry.DoesNotExist:
            return Response(
                {"detail": "Queue entry not found."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = JoinOpenSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            usernames = services.verify_pair_credentials(
                [serializer.validated_data["credentials"]], entry.court.location
            )[0]
            requesting_user = User.objects.get(username=usernames[0])
            entry = services.join_open_slot(
                entry=entry, usernames=usernames, requesting_user=requesting_user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(QueueEntrySerializer(entry).data)


class UnsignView(APIView):
    """Public kiosk endpoint — identity comes from credentials submitted
    alongside pair_id, not a session. Superseded as the frontend's primary
    unsign path by QuickUnsignView below (which doesn't require knowing a
    pair_id), but still valid and still tested."""

    permission_classes = [AllowAny]

    def post(self, request, pk):
        try:
            entry = QueueEntry.objects.get(pk=pk)
        except QueueEntry.DoesNotExist:
            return Response(
                {"detail": "Queue entry not found."}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = UnsignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            requesting_user = services.verify_credential(data["username"], data["password"])
            entry = services.unsign_pair(
                entry=entry, pair_id=data["pair_id"], requesting_user=requesting_user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(QueueEntrySerializer(entry).data)


class QuickUnsignView(APIView):
    """The Overview kiosk's quick-unsign widget: 1 or 2 groups of 2
    players' credentials, no pair_id needed — services.unsign_by_credentials
    finds each group's shared pair and unsigns them (validating, for a
    4-player unsign, that both pairs belong to the same QueueEntry)."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = QuickUnsignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entry = services.unsign_by_credentials(serializer.validated_data["pairs"])
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(QueueEntrySerializer(entry).data)


class MemberCheckInView(APIView):
    """Public kiosk endpoint: a member checks in by phone number alone, no
    password. Draws and returns a fresh animal-only password on a match;
    no session/token is created either way."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MemberCheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user, plaintext = services.member_check_in(data["phone_number"], data["location_id"])
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        display_name = getattr(user, "player", None)
        display_name = display_name.display_name if display_name else user.username
        return Response({
            "username": user.username,
            "display_name": display_name,
            "password": plaintext,
        })
