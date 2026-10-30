# Connect phone Jarvis to your Ollama PC

Goal: talk to the model running on your PC from Jarvis on your iPhone, anywhere.

Your phone can't reach your PC directly, so we expose Ollama through a
**Cloudflare tunnel** — the same kind you already use for ai.serverborn.com.
It's free, gives you an HTTPS address automatically, and needs no port
forwarding or firewall changes.

**One real limitation up front:** your PC has to be powered on and awake for
Jarvis to reach it. When the PC is asleep, switch Jarvis's brain back to Claude
in the gear menu.

---

## Step 1 — Let Ollama answer browser calls

By default Ollama refuses calls that come from a web page. Tell it to allow
Jarvis's page. Set two environment variables, then restart Ollama.

**Windows:** open PowerShell and run:
```powershell
setx OLLAMA_ORIGINS "https://data.forgedbyfreedom.org"
```
Then fully quit Ollama (right-click the tray icon → Quit) and start it again.

**Mac:** run:
```bash
launchctl setenv OLLAMA_ORIGINS "https://data.forgedbyfreedom.org"
```
Then quit and reopen the Ollama app.

(Ollama already listens on `127.0.0.1:11434`, which is all the tunnel needs, so
you do **not** need to change OLLAMA_HOST.)

## Step 2 — Install cloudflared on the PC

- **Windows:** download and run the installer from
  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
- **Mac:** `brew install cloudflared`

## Step 3 — Point a tunnel at Ollama

Run these once, in a terminal / PowerShell:

```bash
cloudflared tunnel login
cloudflared tunnel create jarvis-ollama
cloudflared tunnel route dns jarvis-ollama ollama.serverborn.com
```

Create a config file so the tunnel forwards to Ollama. Put this in
`~/.cloudflared/config.yml` (Windows: `C:\Users\<you>\.cloudflared\config.yml`):

```yaml
tunnel: jarvis-ollama
credentials-file: <path printed by the "create" command above>

ingress:
  - hostname: ollama.serverborn.com
    service: http://127.0.0.1:11434
  - service: http_status:404
```

Start it:
```bash
cloudflared tunnel run jarvis-ollama
```

To keep it running after reboot: `cloudflared service install` (Windows/Mac),
or add it to Login Items / a service. Leave the tunnel running whenever you
want Jarvis to reach the PC.

## Step 4 — Point Jarvis at it

On your phone, in Jarvis: gear icon → **My Ollama** →
- **Server URL:** `https://ollama.serverborn.com`
- **Model name:** whichever model you pulled (run `ollama list` on the PC to see
  the exact names)

Save. The header flips to **LOCAL** and Jarvis now runs on your model. Ask it
anything — and the FBF knowledge base toggle still works on the local model too.

---

## Security note (worth 60 seconds)

As written, anyone who guesses `ollama.serverborn.com` can use your PC's model.
Two easy ways to lock it to just you, when you're ready:
- **Cloudflare Access** in front of the hostname (email or PIN login), or
- a simple secret header the tunnel checks.

Ask Jarvis to set either up and he'll give you the exact config. For a quick
first test it's fine to leave it open, then lock it down.
