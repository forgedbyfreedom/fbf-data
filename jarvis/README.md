# Jarvis — Your AI Voice Assistant

A full-service AI voice assistant that runs on your computer. Talk to it out
loud, and it talks back — and it can actually **do** things for you:

- **Run tasks on your computer** — "clean up my downloads folder", "how much disk space do I have?"
- **Open anything** — "open YouTube", "launch Spotify", "open my documents folder"
- **Read and write files** — "write me a grocery list and save it to my desktop"
- **Search the web** — "what's the weather tomorrow?", "who won the game last night?"
- **Remember things** — "remember that my truck takes 5W-30 oil" (it keeps a memory file between sessions)

It has two ways to chat: **voice mode** (microphone + spoken replies) and
**text mode** (type in a window, no microphone needed).

Powered by Claude (Anthropic). Safety built in: Jarvis shows you every
computer command it wants to run and waits for your OK before running it.

---

## Setup (about 10 minutes, one time)

### Step 1 — Install Python

- **Windows:** download Python from https://www.python.org/downloads/ and run the
  installer. **Important:** check the box that says *"Add Python to PATH"* on the
  first screen.
- **Mac:** Python 3 is usually already installed. To check, open the Terminal app
  and type `python3 --version`. If it prints a version number, you're good.

### Step 2 — Download Jarvis

Download this `jarvis` folder to your computer (from GitHub: green **Code**
button → **Download ZIP**, then unzip and find the `jarvis` folder inside).
Put it somewhere easy, like your Documents folder.

### Step 3 — Install Jarvis's parts

Open a terminal **in the jarvis folder**:

- **Windows:** open the jarvis folder in File Explorer, click the address bar,
  type `cmd` and press Enter.
- **Mac:** open Terminal, type `cd ` (with a space), drag the jarvis folder
  into the window, press Enter.

Then run:

```
pip install -r requirements.txt
```

(on Mac use `pip3` instead of `pip`)

**Mac only:** if you see an error about "portaudio" while installing, run
`brew install portaudio` first, then run the pip command again. (If you don't
have brew: https://brew.sh)

### Step 4 — Give Jarvis its brain (API key)

Jarvis thinks using Claude, which needs an API key:

1. Go to https://console.anthropic.com and sign in (or create an account).
2. Go to **Settings → API keys** and click **Create Key**. Copy it.
3. In the jarvis folder, make a copy of the file `.env.example` and rename the
   copy to just `.env`
4. Open `.env` in any text editor and replace the placeholder with your real
   key, so it reads: `ANTHROPIC_API_KEY=sk-ant-...your key...`

Note: the API is pay-as-you-go — normal chatting costs pennies. You may need
to add a small credit balance in the console under **Plans & billing**.

---

## Using Jarvis

From a terminal in the jarvis folder:

| What you want | Command |
|---|---|
| Voice mode (press Enter, then speak) | `python jarvis.py` |
| Hands-free (just say "Jarvis, ...") | `python jarvis.py --wake` |
| Text mode (no microphone) | `python jarvis.py --text` |

(on Mac use `python3`)

Say or type **"goodbye"** to exit.

### Things to try

- "Jarvis, what's the weather looking like this weekend?"
- "Open YouTube and remember that I like fishing videos"
- "What's taking up space on my computer?"
- "Write a workout plan and save it to my desktop"
- "Remember that my wifi password is in the kitchen drawer"

---

## Troubleshooting

**"No API key found"** — Step 4 isn't finished. Make sure the file is named
exactly `.env` (not `.env.txt`) and contains your real key.

**Voice mode won't start / PyAudio errors** — your microphone libraries didn't
install. Run `python jarvis.py --text` to use Jarvis without a microphone, or:
- Windows: `pip install pipwin` then `pipwin install pyaudio`
- Mac: `brew install portaudio` then `pip3 install pyaudio`
- Linux: `sudo apt install portaudio19-dev espeak` then `pip install pyaudio`

**Jarvis can't hear you** — check your microphone is plugged in and allowed:
on Mac, System Settings → Privacy & Security → Microphone → allow Terminal.

**No spoken replies on Linux** — install espeak: `sudo apt install espeak`

---

## Safety notes

- Jarvis asks before running any command on your computer. Only approve
  commands you understand, especially anything that deletes things.
- `--yolo` mode skips those confirmations — convenient, but use with care.
- Your memory file (`jarvis_memory.md`) is plain text on your computer. Don't
  ask Jarvis to remember passwords or other secrets.
