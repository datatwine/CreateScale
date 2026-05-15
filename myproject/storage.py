from whitenoise.storage import CompressedManifestStaticFilesStorage


class ForgivingStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    CompressedManifestStaticFilesStorage gives us:
      - Hash-busted filenames for cache-busting
      - Pre-compressed .gz and .br files for fast serving
      - Immutable cache headers on hashed files

    manifest_strict = False adds resilience:
      - Missing files return the unhashed URL instead of crashing
      - Prevents a single missing static file from taking down the page
    """
    manifest_strict = False
