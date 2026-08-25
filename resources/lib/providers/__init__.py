"""Provider factory — picks the configured source provider."""
from .. import config
from .base import Provider, Stream
from .comet import CometProvider


def get_provider() -> Provider:
    name = config.provider()
    key = config.torbox_token()
    # Torrentio/StremThru adapters land here later; Comet is the default today.
    if name == "torrentio":
        # not yet implemented — fall back to Comet so the app still works
        return CometProvider(key)
    return CometProvider(key)
