"""
Mobile OAuth API — single endpoint for all 3 providers.
POST /api/auth/oauth/
Body: {"provider": "google|twitter|linkedin", ...provider-specific fields}

Google:   sends {"provider":"google",   "token": "<id_token>"}
Twitter:  sends {"provider":"twitter",  "code": "...", "redirect_uri": "...", "code_verifier": "..."}
LinkedIn: sends {"provider":"linkedin", "code": "...", "redirect_uri": "..."}

Returns: {"token": "<DRF token>", "user_id": 1, "username": "..."}
"""
import requests as http_requests

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class SocialLoginAPIView(APIView):
    """One endpoint, three providers. Mobile sends raw token/code, we handle the rest."""

    permission_classes = [AllowAny]

    HANDLERS = {
        "google": "_handle_google",
        "twitter": "_handle_twitter",
        "linkedin": "_handle_linkedin",
    }

    def post(self, request):
        provider = request.data.get("provider", "").lower()
        handler_name = self.HANDLERS.get(provider)
        if not handler_name:
            return Response({"detail": f"Unknown provider: {provider}"}, status=400)
        user_info = getattr(self, handler_name)(request.data)
        if user_info is None:
            return Response({"detail": f"{provider} authentication failed"}, status=400)
        return self._get_or_create_user(user_info)

    # ── Google: verify ID token ──────────────────────────────────
    def _handle_google(self, data):
        id_tok = data.get("token")
        if not id_tok:
            return None
        try:
            from google.auth.transport import requests as google_transport
            from google.oauth2 import id_token as google_id_token

            info = google_id_token.verify_oauth2_token(
                id_tok, google_transport.Request(), audience=None
            )
            valid_auds = [
                settings.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["client_id"],
                getattr(settings, "GOOGLE_IOS_CLIENT_ID", ""),
            ]
            if info.get("aud") not in [a for a in valid_auds if a]:
                return None
            return {
                "email": info.get("email"),
                "first_name": info.get("given_name", ""),
                "last_name": info.get("family_name", ""),
                "provider": "google",
            }
        except Exception:
            return None

    # ── Twitter: exchange auth code server-side ──────────────────
    def _handle_twitter(self, data):
        code = data.get("code")
        redirect_uri = data.get("redirect_uri", "")
        code_verifier = data.get("code_verifier", "")
        if not code:
            return None
        try:
            tok_resp = http_requests.post(
                "https://api.twitter.com/2/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.SOCIALACCOUNT_PROVIDERS["twitter_oauth2"]["APP"]["client_id"],
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                },
                timeout=15,
            )
            if tok_resp.status_code != 200:
                return None
            access_token = tok_resp.json().get("access_token")
            if not access_token:
                return None
            me_resp = http_requests.get(
                "https://api.twitter.com/2/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"user.fields": "id,name,username"},
                timeout=10,
            )
            if me_resp.status_code != 200:
                return None
            tw = me_resp.json().get("data", {})
            return {
                "email": None,
                "first_name": tw.get("name", ""),
                "last_name": "",
                "twitter_username": tw.get("username", ""),
                "provider": "twitter",
            }
        except Exception:
            return None

    # ── LinkedIn: exchange auth code server-side ─────────────────
    def _handle_linkedin(self, data):
        code = data.get("code")
        redirect_uri = data.get("redirect_uri", "")
        if not code:
            return None
        try:
            tok_resp = http_requests.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.SOCIALACCOUNT_PROVIDERS["linkedin_oauth2"]["APP"]["client_id"],
                    "client_secret": settings.SOCIALACCOUNT_PROVIDERS["linkedin_oauth2"]["APP"]["secret"],
                    "redirect_uri": redirect_uri,
                },
                timeout=15,
            )
            if tok_resp.status_code != 200:
                return None
            access_token = tok_resp.json().get("access_token")
            if not access_token:
                return None
            me_resp = http_requests.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if me_resp.status_code != 200:
                return None
            li = me_resp.json()
            return {
                "email": li.get("email"),
                "first_name": li.get("given_name", ""),
                "last_name": li.get("family_name", ""),
                "provider": "linkedin",
            }
        except Exception:
            return None

    # ── Shared: find-or-create user, return DRF token ────────────
    def _get_or_create_user(self, info):
        email = (info.get("email") or "").lower().strip()

        # Twitter often has no email — use twitter_username as fallback
        if not email and info.get("twitter_username"):
            email = f"{info['twitter_username']}@twitter.placeholder"

        if not email:
            return Response({"detail": "No email from provider"}, status=400)

        user = User.objects.filter(email=email).first()
        if not user:
            base = email.split("@")[0]
            username = base
            n = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}{n}"
                n += 1
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=info.get("first_name", ""),
                last_name=info.get("last_name", ""),
            )
            user.set_unusable_password()
            user.save()

        token, _ = Token.objects.get_or_create(user=user)
        return Response({
            "token": token.key,
            "user_id": user.id,
            "username": user.username,
        })
