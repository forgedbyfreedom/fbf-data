# Jarvis long-term memory

One line per fact, newest at the bottom. Jarvis reads this at the start of
every session and appends here when asked to remember something.

- (2026-07-05) Jarvis was created today: a voice assistant app (jarvis/jarvis.py) plus a persona that loads in every Claude Code session on this repo.
- (2026-07-05) Owner is job hunting: leadership development, corporate fitness/wellness, emergency mgmt exec roles; min $125K; remote or ~45 min of Chapin, SC. Daily automated search set up — config in jarvis/job-search/, digest lands as a Gmail draft + notification each morning.
- (2026-07-05) HARD RULE: never apply to / prepare applications for State of South Carolina jobs (he works for SCDC) without Bryan's direct permission.
- (2026-07-05) Bryan has zero college (HS Regents Diploma only) — never state/imply a degree; lean on 31 yrs experience, SES rank, books, certs. Flag degree-required postings rather than skipping.
- (2026-07-05) Bryan's fitness credentials: NASM Certified Personal Trainer, nutrition coach, physique & bodybuilding coach, meal prep coach. Also SCDC AI Committee Chairperson.
- (2026-07-05) Owner is Bryan Antonelli, Chapin SC: 31-yr corrections exec (SES, ex-BOP Complex Warden/Regional Director, now SC DOC Asst Deputy Director), USAF veteran, published leadership author, national-record powerlifter, BJJ black belt. Master résumé in jarvis/job-search/base-resume.md (sanitized — repo main is public via GitHub Pages at data.forgedbyfreedom.org; never commit his address/phone).
- (2026-10-30) Phone Jarvis (data.forgedbyfreedom.org/jarvis) upgraded: gear-menu toggle to run on Claude OR a self-hosted Ollama model; FBF knowledge-base hookup for fitness/nutrition/health questions (routes to forgedbyfreedom.net growth/ask); voice picker + speed slider. The original 400 error was a non-workspace Claude key — fix is pasting a workspace-scoped key in the gear menu.
- (2026-10-30) PENDING: (1) FBF knowledge base needs the WordPress CORS snippet applied (jarvis/FBF_KNOWLEDGE_SETUP.md) before the browser can reach it. (2) Ollama move is wired in the UI but needs Bryan to expose his Ollama server over HTTPS + set OLLAMA_ORIGINS, then paste the URL+model in the gear menu. Bryan wants the local/unrestricted model as an option alongside Claude.
