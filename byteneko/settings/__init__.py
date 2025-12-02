"""Dynamic settings loader for ByteNeko."""

import os


def _get_env() -> str:
    """Return the active environment, defaulting to ``local`` for dev."""
    env = os.environ.get('DJANGO_ENV') or 'local'
    os.environ.setdefault('DJANGO_ENV', env)
    return env


_DJANGO_ENV = _get_env()

if _DJANGO_ENV == 'production':
    from .production import *  # noqa: F401,F403
elif _DJANGO_ENV == 'base':
    from .base import *  # noqa: F401,F403
else:
    # Default to local settings for developer convenience
    from .local import *  # noqa: F401,F403