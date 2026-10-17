# Customizing Sophie

Everything about who Sophie is and how she behaves lives in a few small, plain-text files. You don't need to know Python to change them: open the file, edit the text between the quotes, save, restart.

Every command below can be copy-pasted into a terminal from inside the project folder (`cd sophie-ai` first). The "edit" commands open the file in a normal text editor window: type, then `Ctrl+S` to save. They use `gnome-text-editor` (Ubuntu's default). Swap in `gedit`, `kate`, `code` or any editor you like.

To open the whole project folder in your file manager instead:

```bash
xdg-open . &
```

> **After editing any `.py` file, restart `web.py`** (`Ctrl+C` in its terminal, then `python web.py` again).
> The `.json` files (`seed_memory.json`, `learned_profile.json`, `mood_state.json`, `history.json`) are re-read on every message, so changes to those take effect immediately.


## How a reply actually gets built

Read this before editing anything prompt-related: it explains why several files all feed into one reply.

Every reply is one call to your LLM, with a system prompt assembled fresh each turn from four layers, in this order:

1. **`prompt.py`'s `BASE_PROMPT`:** her fixed personality.
2. **`seed_memory.json` + `learned_profile.json`, merged:** "Things you know about the user: ..."
3. **A one-line time note:** how long since you last talked.
4. **`mood.py`'s current mood instruction:** blank when the mood is neutral.

So editing `prompt.py` changes layer 1, but what she says is still shaped by memory (layer 2) and mood (layer 4) on top of it. They aren't separate features; they all land in the same prompt.


## 1. Her personality: `prompt.py`

```bash
gnome-text-editor prompt.py &
```

`BASE_PROMPT` is one block of text that tells the LLM who she is. It has three parts:

- **Identity:** her name, and that she's a fictional character in a conversation with the user.
- **Who you are:** background and personality traits she can draw on. Change these freely: age, job, hobbies, sense of humour, temperament.
- **How you talk:** the rules that make her sound like a person speaking rather than an assistant writing. **Keep the length rule** ("one to three sentences"). Long replies take longer to speak, and they're the first thing that makes a voice companion feel unnatural.

Tips:
- Describe her the way you'd brief an actor: traits and attitude, not a script.
- If she keeps doing something you dislike (a catchphrase, starting with your name), add a plain "Don't ..." line under "How you talk".
- To rename her, also change "Sophie" in `mood.py`'s `MOOD_CLASSIFY_PROMPT` and the `<title>` in `templates/index.html`.


## 2. How much she leads vs. follows (her "dominance"): `mood.py`

```bash
gnome-text-editor mood.py &
```

Sophie doesn't have one fixed level of assertiveness. After every reply, a background pass reads the last few turns and decides her **stance for the next reply**. This is why a mood change shows up one turn later, not instantly. The current stance is stored in `mood_state.json`.

The built-in stances:

| Stance | When it's picked | What she does |
|---|---|---|
| `leading` | You're quiet, giving short answers, or say "you pick" | Takes charge: brings up her own stuff, changes the topic, drives the conversation |
| `following` | You're telling a story or asking about something specific | Lets you lead, stays on your topic |
| `playful` | You're joking or the conversation is light | Teases, keeps it quick and fun |
| `supportive` | You sound stressed, tired or down | Calm, slower, listens more than she talks |
| `neutral` | Nothing in particular | Just her base personality |

There are two dials in this file.

**`DYNAMIC_INSTRUCTIONS`: what each stance makes her do.** This is the main dial. Each entry is the exact sentence added to her prompt while she's in that stance. For example, to make her lead **much more strongly**, change the `leading` text to something like:

```python
"leading": (
    "Right now you're firmly in charge of this conversation. Don't ask what the user "
    "wants to talk about: decide. Make strong statements, give your opinion first, "
    "and steer the topic wherever you want it to go."
),
```

Or tone it down:

```python
"leading": (
    "The user is a bit quiet, so gently offer something of your own to talk about."
),
```

**`MOOD_CLASSIFY_PROMPT`: when she switches stance.** This is the rule list the background pass follows. To make her lead **more often**, loosen the `"leading"` rule (for example "...or whenever the user's reply is under ten words"). To make her lead **less often**, tighten it. The line "Prefer keeping the current dynamic... Do not flip on a single ambiguous or short line" controls how quickly she changes stance. Remove it and she'll react faster; make it stricter and she'll be steadier.

**Make a stance her default:** change `DEFAULT_STATE` (for example `{"dynamic": "leading", "energy": 0.5}`), then reset `mood_state.json` (see [Starting fresh](#starting-fresh)).

**Turn moods off completely:** set every entry in `DYNAMIC_INSTRUCTIONS` to `""`. She'll then always be just `prompt.py`.

**Add your own stance:** add a new entry to `DYNAMIC_INSTRUCTIONS`, for example `"sarcastic": "You're in a dry, sarcastic mood..."`. Then describe in `MOOD_CLASSIFY_PROMPT` when to pick it, and add its name to the list of allowed values in two places there: the `"dynamic": one of ...` line and the "one of the five states" line at the bottom. The classifier can only choose stances it's told about.

**Check or reset her current stance:**

```bash
gnome-text-editor mood_state.json &
```

The terminal running `web.py` also prints `[mood] -> {...}` after every reply, so you can watch it change.


## 3. What she knows about you

**`seed_memory.json`:** facts you plant before you've said a word. It's always included and never changed automatically. Start from the example:

```bash
cp seed_memory.example.json seed_memory.json
gnome-text-editor seed_memory.json &
```

```json
{
  "name": "Alex",
  "location": "somewhere sunny",
  "job": "nurse, works night shifts"
}
```

**`learned_profile.json`:** grows on its own. After each exchange, a background pass (`extraction.py`) reads only *your* last line and records any new fact you revealed about yourself. Edit it freely, or empty it to `{}` to make her forget.

```bash
gnome-text-editor learned_profile.json &
```

If she's "learning" things that aren't true, or missing things that are, edit the rules in `EXTRACTION_PROMPT`:

```bash
gnome-text-editor extraction.py &
```


## 4. What she brings up when it's quiet: `topic_starters.py`

```bash
gnome-text-editor topic_starters.py &
```

- **`TOPIC_STARTERS`:** lines she says on her own after a quiet spell, written exactly as she'll speak them. Add as many as you like.
- **`GIVE_UP_LINES`:** what she says if she brings something up and you don't answer.

About 30% of the time she shares a random Wikipedia fact instead (see `INTERNET_TOPIC_CHANCE` below).


## 5. Timings and interruptions: `config.py`

```bash
gnome-text-editor config.py &
```

| Setting | What it does |
|---|---|
| `IDLE_THRESHOLD_SECONDS` | How long it must be quiet before she brings something up |
| `RESPONSE_TIMEOUT_SECONDS` | How long she waits for an answer before giving up on her topic |
| `INTERNET_TOPIC_CHANCE` | Odds of a Wikipedia fact instead of a `topic_starters.py` line (`0` = never, `1` = always) |
| `MAX_HISTORY` | How many recent messages she sees each turn (her short-term memory) |
| `REPLY_MAX_TOKENS` | Hard cap on reply length |
| `VAD_MIN_SILENCE_MS` | How long you must pause before she decides you've finished talking. Raise it if she cuts you off mid-thought |
| `VAD_THRESHOLD` | Mic sensitivity (0-1). Raise it if background noise triggers her |
| `TRIGGER_WORDS` | Words that always interrupt her ("stop", "wait", ...) |
| `BACKCHANNEL_PHRASES` | Words that never interrupt her ("yeah", "mhm", ...) |

The LLM temperature (how adventurous her wording is) is in `web.py`'s `get_reply()`: `temperature=0.75`. Lower means more predictable; higher means more varied.


## 6. Her voice

Replace `voice_ref/sample.wav` with 5-20 seconds of one person speaking clearly. Calm, natural speech clones best. Restart `web.py`. Only use a voice you have permission to use.


## Starting fresh

`seed_memory.json` isn't part of this. It's the facts you deliberately planted, so wiping it is a separate choice.

To reset everything she has picked up on her own, stop `web.py` first, then:

```bash
echo '[]' > history.json
echo '{}' > learned_profile.json
echo '{"dynamic": "neutral", "energy": 0.5}' > mood_state.json
> conversation_log.txt
rm -rf audio_history
```

Then start `web.py` again.


## All the files at a glance

| File | What it is | Edit it? |
|---|---|---|
| `prompt.py` | Her personality | Yes |
| `mood.py` | Stances, and when she switches between them | Yes |
| `topic_starters.py` | Idle conversation starters | Yes |
| `seed_memory.json` | Facts you plant about yourself | Yes |
| `config.py` | Timings, interrupt words, sensitivity | Yes |
| `extraction.py` | Rules for what she learns about you | Sometimes |
| `learned_profile.json` | What she has learned (auto) | To correct or forget |
| `mood_state.json` | Her current stance (auto) | To reset |
| `history.json` | Recent conversation she sees (auto) | To clear |
| `conversation_log.txt` | Readable transcript, not fed back to her | No |
| `web.py`, `vad.py`, `stt.py`, `idle.py` | The voice pipeline | Only if you're comfortable with code |
