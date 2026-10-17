# idle.py
#
# The "pull something random from the internet" half of the idle-topic
# system (the other half is the manually-written topic_starters.py). Uses
# Wikipedia's random-article summary endpoint — free, no API key, no signup.

import json
import urllib.request

WIKI_RANDOM_URL = "https://en.wikipedia.org/api/rest_v1/page/random/summary"


def get_internet_topic(timeout=4):
    """Return (title, extract) for a random Wikipedia article, or None if the
    fetch fails for any reason (offline, timeout, etc). Callers should treat
    None as "fall back to topic_starters.py"."""
    try:
        req = urllib.request.Request(
            WIKI_RANDOM_URL,
            headers={"User-Agent": "sophie-ai-dev/1.0 (personal project)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        title = data.get("title", "").strip()
        extract = data.get("extract", "").strip()
        if title and extract:
            return title, extract
    except Exception as e:
        print(f"[idle] internet topic fetch failed: {e}")
    return None
