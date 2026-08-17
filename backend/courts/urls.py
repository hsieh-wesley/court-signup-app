from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("courts/", views.CourtListView.as_view(), name="court-list"),
    path("me/status/", views.MyStatusView.as_view(), name="my-status"),
    path("queue-entries/", views.QueueEntryCreateView.as_view(), name="queue-entry-create"),
    path(
        "queue-entries/<int:pk>/join/",
        views.JoinOpenSlotView.as_view(),
        name="queue-entry-join",
    ),
    path(
        "queue-entries/<int:pk>/unsign/",
        views.UnsignView.as_view(),
        name="queue-entry-unsign",
    ),
]
