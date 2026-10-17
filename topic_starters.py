# topic_starters.py
#
# Lines Sophie can bring up on her own when it's been quiet for a while
# (see IDLE_THRESHOLD_SECONDS in config.py). Write them exactly the way you
# want her to actually say them — add as many as you like, one string per
# entry. When one gets used, the user's reply (if any) flows through the
# normal chat pipeline and extraction.py, so whatever they tell you gets
# remembered.

TOPIC_STARTERS = [
    "Okay, random question. What's the best thing you've eaten this week?",
    "I've had the same song stuck in my head all day. What are you listening to lately?",
    "If you could be anywhere right now, where would it be?",
    "What's something you've been meaning to try but keep putting off?",
    "Tell me something that made you laugh recently.",
]

# What Sophie says if she brings something up and gets no reply within
# RESPONSE_TIMEOUT_SECONDS (config.py). Picked at random so it doesn't
# sound identical every time.
GIVE_UP_LINES = [
    "Ok, guess you don't want to talk about that.",
    "Fair enough, I'll drop it.",
    "No worries, forget I said anything.",
    "Alright, moving on then.",
]
