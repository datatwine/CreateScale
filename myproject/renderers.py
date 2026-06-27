import orjson
from rest_framework.renderers import BaseRenderer
from rest_framework.utils.encoders import JSONEncoder

_drf_default = JSONEncoder().default


class ORJSONRenderer(BaseRenderer):
    media_type = "application/json"
    format = "json"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""

        opts = orjson.OPT_NON_STR_KEYS | orjson.OPT_PASSTHROUGH_DATETIME

        if (renderer_context or {}).get("indent"):
            opts |= orjson.OPT_INDENT_2

        return orjson.dumps(data, default=_drf_default, option=opts)
