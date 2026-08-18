from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import admin_services, services
from .models import Court, Location, QueueEntry
from .permissions import TempAccountNotExpired
from .serializers import (
    CourtBoardSerializer,
    CreateQueueEntrySerializer,
    JoinOpenSlotSerializer,
    LocationSerializer,
    QueueEntrySerializer,
    UnsignSerializer,
)

User = get_user_model()


class LoginView(APIView):
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
        elif not user.is_staff:
            return Response(
                {"detail": "location_id is required."}, status=status.HTTP_400_BAD_REQUEST
            )

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
        available = bool(username) and not User.objects.filter(username=username).exists()
        return Response({"available": available})


class RegisterPlayerView(APIView):
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

        session = services.create_player_session(player.user, location)
        return Response(
            {
                "token": session.key,
                "username": player.user.username,
                "password": plaintext,
                "is_staff": False,
                "location_id": location.id,
                "location_name": location.name,
            },
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


class MyStatusView(APIView):
    permission_classes = [IsAuthenticated, TempAccountNotExpired]

    def get(self, request):
        entries = (
            QueueEntry.objects.filter(
                Q(pairs__player_1=request.user) | Q(pairs__player_2=request.user),
                status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
                court__location=request.auth.location,
            )
            .distinct()
            .order_by("created_at", "id")
        )
        return Response(QueueEntrySerializer(entries, many=True).data)


class QueueEntryCreateView(APIView):
    permission_classes = [IsAuthenticated, TempAccountNotExpired]

    def post(self, request):
        serializer = CreateQueueEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        court = serializer.validated_data["court_id"]
        if court.location_id != request.auth.location_id:
            return Response(
                {"detail": "This court belongs to a different facility."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            pairs = services.verify_pair_credentials(
                serializer.validated_data["pairs"], request.user
            )
            entry = services.create_queue_entry(
                court=court, pairs=pairs, created_by=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(
            QueueEntrySerializer(entry).data, status=status.HTTP_201_CREATED
        )


class JoinOpenSlotView(APIView):
    permission_classes = [IsAuthenticated, TempAccountNotExpired]

    def post(self, request, pk):
        try:
            entry = QueueEntry.objects.get(pk=pk)
        except QueueEntry.DoesNotExist:
            return Response(
                {"detail": "Queue entry not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if entry.court.location_id != request.auth.location_id:
            return Response(
                {"detail": "This court belongs to a different facility."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = JoinOpenSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            usernames = services.verify_pair_credentials(
                [serializer.validated_data["credentials"]], request.user
            )[0]
            entry = services.join_open_slot(
                entry=entry, usernames=usernames, requesting_user=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(QueueEntrySerializer(entry).data)


class UnsignView(APIView):
    permission_classes = [IsAuthenticated, TempAccountNotExpired]

    def post(self, request, pk):
        try:
            entry = QueueEntry.objects.get(pk=pk)
        except QueueEntry.DoesNotExist:
            return Response(
                {"detail": "Queue entry not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if entry.court.location_id != request.auth.location_id:
            return Response(
                {"detail": "This court belongs to a different facility."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UnsignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pair_id = serializer.validated_data["pair_id"]
        try:
            entry = services.unsign_pair(
                entry=entry, pair_id=pair_id, requesting_user=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        return Response(QueueEntrySerializer(entry).data)
