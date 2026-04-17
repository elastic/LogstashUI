#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.


class NoAuthMiddleware:
    """
    Sandbox middleware: auto-authenticates every request as the first active user.
    If no users exist, creates a default admin account automatically.
    Only active when NO_AUTH_MODE is enabled in config. Never use in production.
    """

    _no_auth_user_cache = None

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            user = self._get_or_create_no_auth_user()
            if user:
                request.user = user
        return self.get_response(request)

    def _get_or_create_no_auth_user(self):
        import logging
        logger = logging.getLogger(__name__)

        if NoAuthMiddleware._no_auth_user_cache is not None:
            return NoAuthMiddleware._no_auth_user_cache

        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            user = User.objects.filter(is_active=True).first()
            if user is None:
                user = self._create_no_auth_admin(User, logger)

            NoAuthMiddleware._no_auth_user_cache = user
            return user
        except Exception:
            # DB may not be ready (e.g. pre-migration). Fall through gracefully.
            return None

    def _create_no_auth_admin(self, User, logger):
        from django.db import transaction
        try:
            with transaction.atomic():
                # Re-check inside the transaction to avoid races
                if User.objects.exists():
                    return User.objects.filter(is_active=True).first()
                user = User.objects.create_superuser(
                    username='admin',
                    email='',
                    password=None,  # unusable password — login form won't work
                )
                logger.warning(
                    "NO_AUTH MODE: No users found — created default 'admin' account "
                    "with an unusable password."
                )
                return user
        except Exception as e:
            logger.error(f"NO_AUTH MODE: Failed to create default admin user: {e}")
            return None


class SecurityHeadersMiddleware:
    """
    Middleware to add Content Security Policy and other security headers.
    Restricts iframe sources to trusted documentation domains.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Content Security Policy
        # frame-src: Controls which URLs can be loaded in iframes
        # 'self': Allow iframes from same origin
        # Trusted documentation domains for plugin docs
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # unsafe-inline/eval needed for htmx and dynamic JS
            "style-src 'self' 'unsafe-inline'",  # unsafe-inline needed for Tailwind
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-src 'self' https://www.elastic.co https://elastic.co https://github.com https://rubydoc.info",
            "frame-ancestors 'self'",  # Prevent this site from being framed by others
        ]
        
        response['Content-Security-Policy'] = "; ".join(csp_directives)
        
        # Additional security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'no-referrer-when-downgrade'
        
        return response
