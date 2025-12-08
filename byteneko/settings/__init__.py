"""Dynamic settings loader for ByteNeko."""

import os
from pathlib import Path

# Load .env file BEFORE checking DJANGO_ENV
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        # If python-dotenv is not installed, manually parse .env
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())


def _get_env() -> str:
    """Return the active environment, defaulting to ``local`` for dev."""
    env = (os.environ.get('DJANGO_ENV') or 'local').lower()
    os.environ.setdefault('DJANGO_ENV', env)
    return env


_DJANGO_ENV = _get_env()

if _DJANGO_ENV in {'production', 'prod'}:
    from .production import *  # noqa: F401,F403
elif _DJANGO_ENV in {'test', 'testing'}:
    from .test import *  # noqa: F401,F403
elif _DJANGO_ENV == 'base':
    from .base import *  # noqa: F401,F403
else:
    # Default to local settings for developer convenience
    from .local import *  # noqa: F401,F403