from django.urls import path
from . import views
from .admin_views import UserAdminDetailView, UserAdminListCreateView

urlpatterns = [
    path("me", views.MeView.as_view(), name="me-contract"),
    path("utilisateurs", UserAdminListCreateView.as_view(), name="users-contract-list-create"),
    path("utilisateurs/<int:user_id>", UserAdminDetailView.as_view(), name="users-contract-detail"),
    path("auth/login", views.LoginView.as_view(), name="login-contract"),
    path("auth/logout", views.LogoutView.as_view(), name="logout-contract"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/changer-mot-de-passe/", views.ChangerMotDePasseView.as_view(), name="changer-mdp"),
]
