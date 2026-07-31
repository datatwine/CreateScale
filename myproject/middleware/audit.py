import json
import logging
import time

logger = logging.getLogger("audit")


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        if request.user.is_authenticated:
            logger.info(
                json.dumps(
                    {
                        "user": request.user.username,
                        "method": request.method,
                        "path": request.path,
                        "status": response.status_code,
                        "ms": round((time.time() - start) * 1000),
                    }
                )
            )
        return response
