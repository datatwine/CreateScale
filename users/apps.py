from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "users"

    def ready(self):
        import users.signals  # noqa: F401 — side-effect import, activates Django signals
