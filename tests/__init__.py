"""Tests. They check French texts unless they set another language (CEV_LANG)."""

import os

os.environ["CEV_LANG"] = "fr"

# The sounds read aloud go to the user's cache folder (speech.cache_dir): never the real one in the tests.
import tempfile

os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="cev-test-cache-")
