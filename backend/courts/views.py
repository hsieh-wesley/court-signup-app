from django.contrib.auth import authenticate
from django.db.models import Q
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Court, QueueEntry
from .permissions import TempAccountNotExpired
from .serializers import (
    CourtBoardSerializer,
    CreateQueueEntrySerializer,
    JoinOpenSlotSerializer,
    QueueEntrySerializer,
    UnsignSerializer,
)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
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
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {"token": token.key, "username": user.username, "is_staff": user.is_staff}
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.auth_token.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourtListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        services.reap_expired_reservations()
        courts = Court.objects.all().order_by("name")
        return Response(CourtBoardSerializer(courts, many=True).data)


class MyStatusView(APIView):
    permission_classes = [IsAuthenticated, TempAccountNotExpired]

    def get(self, request):
        entries = (
            QueueEntry.objects.filter(
                Q(pairs__player_1=request.user) | Q(pairs__player_2=request.user),
                status__in=[QueueEntry.Status.WAITING, QueueEntry.Status.ACTIVE],
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
        pairs = serializer.validated_data["pairs"]
        try:
            entry = services.create_queue_entry(
                court=court, pairs=pairs, created_by=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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
        serializer = JoinOpenSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usernames = serializer.validated_data["usernames"]
        try:
            entry = services.join_open_slot(
                entry=entry, usernames=usernames, requesting_user=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
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
        serializer = UnsignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pair_id = serializer.validated_data["pair_id"]
        try:
            entry = services.unsign_pair(
                entry=entry, pair_id=pair_id, requesting_user=request.user
            )
        except services.ServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(QueueEntrySerializer(entry).data)
