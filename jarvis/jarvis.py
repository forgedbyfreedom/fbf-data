#!/usr/bin/env python3
"""
Jarvis — a full-service AI voice assistant for your computer.

Talks with you by voice (or text), thinks with Claude, and can actually DO
things on this machine: run commands, open apps and websites, read and write
files, search the web, and remember things between sessions.

Usage:
    python jarvis.py            # voice mode (press Enter, speak, get a spoken reply)
    python jarvis.py --text     # text chat mode (type instead of talking)
    python jarvis.py --wake     # hands-free: listens continuously for "jarvis"
    python jarvis.py --yolo     # skip the confirmation prompt before running commands
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000
JARVIS_DIR = Path(__file__).resolve().parent
MEMORY_FILE = JARVIS_DIR / "jarvis_memory.md"
ENV_FILE = JARVIS_DIR / ".env"

WAKE_WORD = "jarvis"


def load_env_file():
    """Load KEY=VALUE pairs from a .env file next to this script, if present."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_memory() -> str:
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return "(memory is empty so far)"


# ---------------------------------------------------------------------------
# Tools Jarvis can use on this machine
# ---------------------------------------------------------------------------

TOOLS = [
    # Server-side web search — runs on Anthropic's side, no local code needed.
    {"type": "web_search_20260209", "name": "web_search"},
    {
        "name": "run_command",
        "description": (
            "Run a shell command on the user's computer and return its output. "
            "Call this when the user asks you to do something on the machine that "
            "needs the command line: manage files, check disk space, install "
            "software, control processes, git operations, etc. The user is asked "
            "to approve each command before it runs, so prefer one clear command "
            "over many small ones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact shell command to execute.",
                },
                "explanation": {
                    "type": "string",
                    "description": "One plain-English sentence saying what this command does, shown to the user in the approval prompt.",
                },
            },
            "required": ["command", "explanation"],
        },
    },
    {
        "name": "open_item",
        "description": (
            "Open a website, application, file, or folder using the computer's "
            "default handler. Call this whenever the user asks to open, launch, "
            "play, or show something — e.g. 'open YouTube', 'open my Downloads "
            "folder', 'launch Spotify'. For websites, pass a full URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "A URL (https://...), a file/folder path, or an application name.",
                }
            },
            "required": ["target"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a text file from the user's computer and return its contents. "
            "Call this when the user asks about the contents of a specific file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a text file on the user's computer. Call this "
            "when the user asks you to write, save, or create a file, note, "
            "script, or document."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Where to save the file."},
                "content": {"type": "string", "description": "The full file contents."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_folder",
        "description": (
            "List the files and folders inside a directory on the user's "
            "computer. Call this when the user asks what's in a folder, or when "
            "you need to find a file before reading or opening it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The folder to list."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Save a fact to Jarvis's long-term memory file so it persists across "
            "sessions. Call this whenever the user tells you something worth "
            "remembering ('remember that...', preferences, names, recurring "
            "tasks) or asks you to take a note for later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "The fact to remember, written as one short standalone line.",
                }
            },
            "required": ["note"],
        },
    },
]


class ToolExecutor:
    """Executes Jarvis's local tools, with a safety confirmation for commands."""

    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve

    def execute(self, name: str, tool_input: dict) -> tuple[str, bool]:
        """Run one tool. Returns (result_text, is_error)."""
        try:
            handler = getattr(self, f"_do_{name}", None)
            if handler is None:
                return f"Unknown tool: {name}", True
            return handler(tool_input)
        except Exception as exc:  # surface the error to the model so it can adapt
            return f"Error: {exc}", True

    # -- individual tools ---------------------------------------------------

    def _do_run_command(self, tool_input: dict) -> tuple[str, bool]:
        command = tool_input["command"]
        explanation = tool_input.get("explanation", "")
        if not self.auto_approve:
            print(f"\n  Jarvis wants to run:  {command}")
            if explanation:
                print(f"  ({explanation})")
            answer = input("  Allow? [y/N] ").strip().lower()
            if answer not in ("y", "yes"):
                return "The user declined to run this command.", True
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        output = output.strip() or "(command produced no output)"
        if len(output) > 8000:
            output = output[:8000] + "\n...(output truncated)"
        if proc.returncode != 0:
            return f"Command exited with code {proc.returncode}:\n{output}", True
        return output, False

    def _do_open_item(self, tool_input: dict) -> tuple[str, bool]:
        target = tool_input["target"].strip()
        system = platform.system()
        if target.startswith(("http://", "https://")):
            webbrowser.open(target)
            return f"Opened {target} in the browser.", False
        if system == "Windows":
            os.startfile(target)  # noqa: S606 - intentional, user-requested open
        elif system == "Darwin":
            subprocess.run(["open", "-a", target] if not os.path.exists(target) else ["open", target], check=True)
        else:
            subprocess.run(["xdg-open", target], check=True)
        return f"Opened {target}.", False

    def _do_read_file(self, tool_input: dict) -> tuple[str, bool]:
        path = Path(tool_input["path"]).expanduser()
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > 20000:
            text = text[:20000] + "\n...(file truncated)"
        return text, False

    def _do_write_file(self, tool_input: dict) -> tuple[str, bool]:
        path = Path(tool_input["path"]).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tool_input["content"], encoding="utf-8")
        return f"Saved {len(tool_input['content'])} characters to {path}.", False

    def _do_list_folder(self, tool_input: dict) -> tuple[str, bool]:
        path = Path(tool_input["path"]).expanduser()
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [f"{'[dir] ' if p.is_dir() else ''}{p.name}" for p in entries[:200]]
        if len(entries) > 200:
            lines.append(f"...and {len(entries) - 200} more")
        return "\n".join(lines) or "(empty folder)", False

    def _do_remember(self, tool_input: dict) -> tuple[str, bool]:
        stamp = datetime.now().strftime("%Y-%m-%d")
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"- ({stamp}) {tool_input['note']}\n")
        return "Noted — saved to long-term memory.", False


# ---------------------------------------------------------------------------
# The brain: Claude with an agentic tool loop
# ---------------------------------------------------------------------------


def build_system_prompt() -> str:
    return f"""You are Jarvis, a capable, friendly AI voice assistant running on the user's computer.

Environment: {platform.system()} {platform.release()}, Python {platform.python_version()}.
Today's date: {datetime.now().strftime('%A, %B %d, %Y')}.
The user's home folder is {Path.home()}.

You have tools to run commands, open apps/websites/files, read and write files,
list folders, search the web, and save notes to long-term memory. Use them —
when the user asks you to DO something on the machine, act with tools rather
than describing how they could do it themselves. When the answer depends on
current information (news, weather, prices, sports), use web_search before
answering rather than answering from memory.

Your replies are spoken out loud with text-to-speech, so:
- Keep responses short and conversational — one to three sentences for most requests.
- Never use markdown, bullet lists, code blocks, or symbols in your final reply.
- After completing an action, confirm briefly in plain words what you did.

For minor choices, pick a reasonable option and note it rather than asking.
For destructive actions (deleting files, killing processes), state exactly what
will be affected before doing it.

Your long-term memory (facts the user asked you to remember):
{load_memory()}
"""


class Jarvis:
    def __init__(self, executor: ToolExecutor):
        import anthropic  # imported here so --help works without the SDK installed

        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.executor = executor
        self.messages: list = []
        self.system_prompt = build_system_prompt()

    def ask(self, user_text: str, on_status=None) -> str:
        """Send one user turn through the agentic loop; return the final reply."""
        self.messages.append({"role": "user", "content": user_text})

        while True:
            try:
                response = self.client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=self.system_prompt,
                    thinking={"type": "adaptive"},
                    tools=TOOLS,
                    messages=self.messages,
                )
            except self.anthropic.AuthenticationError:
                return (
                    "My API key isn't working. Check the ANTHROPIC_API_KEY line "
                    "in the .env file next to jarvis.py."
                )
            except self.anthropic.RateLimitError:
                return "I'm being rate limited right now. Give me a minute and try again."
            except self.anthropic.APIConnectionError:
                return "I can't reach the internet right now, so my brain is offline."
            except self.anthropic.APIStatusError as exc:
                return f"Something went wrong talking to Claude (error {exc.status_code})."

            # Server-side tool (web search) hit its iteration limit — resume.
            if response.stop_reason == "pause_turn":
                self.messages.append({"role": "assistant", "content": response.content})
                continue

            if response.stop_reason == "refusal":
                self.messages.append(
                    {"role": "assistant", "content": "I can't help with that request."}
                )
                return "Sorry, I can't help with that request."

            if response.stop_reason != "tool_use":
                final_text = " ".join(
                    block.text for block in response.content if block.type == "text"
                ).strip()
                # Store plain text (not raw blocks) so old thinking blocks
                # don't have to be replayed on every subsequent turn.
                self.messages.append(
                    {"role": "assistant", "content": final_text or "Done."}
                )
                return final_text or "Done."

            # Claude wants to use local tools: run them all, return all results.
            self.messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if on_status:
                    on_status(f"[using {block.name}]")
                result_text, is_error = self.executor.execute(block.name, dict(block.input))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                        "is_error": is_error,
                    }
                )
            self.messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Voice: ears (speech-to-text) and mouth (text-to-speech)
# ---------------------------------------------------------------------------


class Voice:
    def __init__(self):
        import pyttsx3
        import speech_recognition as sr

        self.sr = sr
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 180)

    def listen(self, timeout: float = 8, phrase_limit: float = 20) -> str | None:
        """Capture one utterance from the microphone; return text or None."""
        with self.sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.4)
            try:
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
            except self.sr.WaitTimeoutError:
                return None
        try:
            return self.recognizer.recognize_google(audio)
        except self.sr.UnknownValueError:
            return None
        except self.sr.RequestError:
            print("  (speech service unreachable — check your internet connection)")
            return None

    def say(self, text: str):
        self.engine.say(text)
        self.engine.runAndWait()


# ---------------------------------------------------------------------------
# Main loops
# ---------------------------------------------------------------------------

EXIT_WORDS = {"quit", "exit", "goodbye", "good bye", "shut down", "shutdown", "stop listening"}


def text_loop(jarvis: Jarvis):
    print("\nJarvis (text mode). Type your request, or 'quit' to exit.\n")
    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        if not user_text:
            continue
        if user_text.lower() in EXIT_WORDS:
            print("Jarvis: Goodbye.")
            return
        reply = jarvis.ask(user_text, on_status=lambda s: print(f"  {s}"))
        print(f"Jarvis: {reply}\n")


def voice_loop(jarvis: Jarvis, hands_free: bool):
    voice = Voice()
    if hands_free:
        print(f"\nJarvis is listening. Say '{WAKE_WORD}' followed by your request.")
        print("Say 'jarvis shut down' to exit.\n")
    else:
        print("\nJarvis (voice mode). Press Enter, then speak. Ctrl+C to exit.\n")
    voice.say("Jarvis online. How can I help?")

    while True:
        try:
            if hands_free:
                heard = voice.listen(timeout=None, phrase_limit=20)
                if not heard:
                    continue
                lowered = heard.lower()
                if WAKE_WORD not in lowered:
                    continue
                # keep everything after the wake word, if anything
                user_text = lowered.split(WAKE_WORD, 1)[1].strip(" ,.!?") or None
                if user_text is None:
                    voice.say("Yes?")
                    user_text = voice.listen()
                    if not user_text:
                        continue
            else:
                input("Press Enter and speak...")
                print("  (listening)")
                user_text = voice.listen()
                if not user_text:
                    print("  (didn't catch that)")
                    continue
        except KeyboardInterrupt:
            print("\nGoodbye.")
            return

        print(f"You: {user_text}")
        if user_text.lower().strip(" ,.!?") in EXIT_WORDS:
            voice.say("Goodbye.")
            return
        reply = jarvis.ask(user_text, on_status=lambda s: print(f"  {s}"))
        print(f"Jarvis: {reply}\n")
        voice.say(reply)


def main():
    parser = argparse.ArgumentParser(description="Jarvis — AI voice assistant")
    parser.add_argument("--text", action="store_true", help="text chat mode (no microphone needed)")
    parser.add_argument("--wake", action="store_true", help="hands-free mode: listen continuously for the wake word")
    parser.add_argument("--yolo", action="store_true", help="run commands without asking for confirmation")
    args = parser.parse_args()

    load_env_file()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No API key found.")
        print(f"Create a file named .env in {JARVIS_DIR} containing:")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        print("Get a key at https://console.anthropic.com/settings/keys")
        sys.exit(1)

    jarvis = Jarvis(ToolExecutor(auto_approve=args.yolo))

    if args.text:
        text_loop(jarvis)
        return

    try:
        voice_loop(jarvis, hands_free=args.wake)
    except ImportError as exc:
        print(f"Voice libraries not available ({exc}).")
        print("Falling back to text mode. To fix voice, see README troubleshooting.\n")
        text_loop(jarvis)


if __name__ == "__main__":
    main()
