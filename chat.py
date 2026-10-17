# chat.py — terminal test bench (no idle/proactive behavior, that's web.py only)

from openai import OpenAI
from config import API_BASE, MODEL, API_KEY
from prompt import BASE_PROMPT
from memory import (
    load_history,
    save_history,
    load_seed_memory,
    load_learned_profile,
    get_recent_history,
    build_system_prompt,
    get_time_context,
    add_timestamp
)

client = OpenAI(base_url=API_BASE, api_key=API_KEY)

def chat(user_input, history, seed_memory, learned_profile):
    time_context = get_time_context(history)
    system_prompt = build_system_prompt(BASE_PROMPT, seed_memory, learned_profile, time_context)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(get_recent_history(history))
    messages.append({"role": "user", "content": user_input})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.8,
        max_tokens=150,
    )

    reply = response.choices[0].message.content.strip()
    return reply

def main():
    history = load_history()
    seed_memory = load_seed_memory()
    learned_profile = load_learned_profile()

    print("Sophie is ready. Type 'quit' to exit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ["quit", "exit"]:
            break
        if not user_input:
            continue

        reply = chat(user_input, history, seed_memory, learned_profile)
        print(f"\nSophie: {reply}\n")

        user_msg = add_timestamp({"role": "user", "content": user_input})
        assistant_msg = add_timestamp({"role": "assistant", "content": reply})

        history.append(user_msg)
        history.append(assistant_msg)
        save_history(history)

if __name__ == "__main__":
    main()
