"""
Settings package for ByteNeko project.
"""

import os

# Conditional imports based on DJANGO_ENV
if os.environ.get('DJANGO_ENV') == 'local':
    from .local import *
elif os.environ.get('DJANGO_ENV') == 'production':
    from .production import *
else:
    from .base import *