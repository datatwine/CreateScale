"""
Custom LinkedIn adapter for allauth.
Overrides the default adapter which uses LinkedIn's deprecated V1 API
(r_liteprofile, /v2/me, GET token exchange).
Uses the new OpenID Connect /v2/userinfo endpoint instead.
"""
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.providers.linkedin_oauth2.views import (
    LinkedInOAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)


class LinkedInOIDCAdapter(LinkedInOAuth2Adapter):
    # Override: use POST (LinkedIn no longer accepts GET for tokens)
    access_token_method = "POST"

    # Override: use the OpenID Connect userinfo endpoint
    userinfo_url = "https://api.linkedin.com/v2/userinfo"

    def get_user_info(self, token):
        headers = {"Authorization": f"Bearer {token.token}"}
        resp = (
            get_adapter()
            .get_requests_session()
            .get(self.userinfo_url, headers=headers)
        )
        resp.raise_for_status()
        data = resp.json()
        # Map OIDC fields to what allauth's provider.extract_uid() expects
        #   OIDC returns: {"sub": "...", "given_name": "...", "family_name": "...", "email": "..."}
        #   allauth expects: {"id": "...", "firstName": "...", "lastName": "...", ...}
        return {
            "id": data.get("sub"),
            "firstName": data.get("given_name", ""),
            "lastName": data.get("family_name", ""),
            "emailAddress": data.get("email", ""),
        }


# These replace the default views; we wire them up in myproject/urls.py
oauth2_login = OAuth2LoginView.adapter_view(LinkedInOIDCAdapter)
oauth2_callback = OAuth2CallbackView.adapter_view(LinkedInOIDCAdapter)
