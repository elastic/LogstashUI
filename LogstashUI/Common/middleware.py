"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""


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
