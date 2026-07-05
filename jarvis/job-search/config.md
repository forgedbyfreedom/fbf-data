# Daily Job Search — Configuration

Owner: Forgedbyfreedom@gmail.com
Set up: 2026-07-05

## Hard rules

- **NEVER apply to, recommend applying to, or prepare materials for any job
  with the State of South Carolina** (SCDC or any SC state agency) without
  Bryan's direct, explicit permission. He currently works for SCDC. If a
  state-of-SC job looks like a great fit, list it in a clearly separated
  "needs your permission" section of the digest — do not include a tailored
  résumé for it.
- **Use all, assume nothing:** tailor résumés strictly from the documented
  facts in base-resume.md. Reorder, reword, and select — never invent
  titles, dates, metrics, employers, or credentials.

## Criteria

- **Minimum salary:** $125,000/year (flag roles slightly below only if exceptional fit)
- **Location:** Remote, OR within ~45 min drive of Chapin, SC
  (Columbia, Lexington, Irmo, Ballentine, Newberry, Blythewood, West Columbia)
- **Job type:** Full-time preferred
- **Shifts:** Monday–Friday preferred

## Target roles / focus areas

1. Leadership development / organizational development (Director, VP, Head of)
2. Training & development / talent development leadership
3. Corporate fitness / corporate wellness / wellness program leadership
4. Emergency management / crisis management / preparedness leadership
5. Security / corrections / public-safety executive roles
6. Operations leadership (large budgets, multi-site)

## Search queries to rotate daily (Indeed)

Remote:
- "leadership development director"
- "director of organizational development"
- "head of learning and development"
- "wellness program director" / "corporate wellness manager"
- "emergency management director"
- "director of security operations"

Local (search location "Columbia, SC"):
- "director" (broad, filter by fit)
- "training director"
- "corporate wellness"
- "emergency management"
- "operations director"

## Résumé source

`base-resume.md` is the master, built from Bryan's real résumés (civilian,
corporate, emergency-director, and USAJOBS federal versions, uploaded
2026-07-05). It is sanitized — no street address or phone — because this
repo's main branch is publicly served at data.forgedbyfreedom.org. The daily
job gets contact details from its own prompt; never commit them here.

Angle guide when tailoring:
- Leadership development / OD roles → lead with leadership programs
  ("Back to the Basics" agency-wide program, facility-tailored programs at
  SCDC), coaching, published author.
- Emergency management roles → lead with Chief of Emergency Preparedness,
  ICS/NIMS/FEMA, Hurricane Michael incident command, D.C. deployment.
- Corporate fitness / wellness roles → lead with NASM CPT, nutrition/meal
  prep/physique & bodybuilding coaching, powerlifting national records, BJJ
  black belt + the leadership/ops record as differentiator.
- Innovation/AI-adjacent leadership roles → note SCDC AI Committee
  Chairperson.
- Operations/security executive roles → lead with SES rank, 24 institutions,
  $980M budget, turnaround results ($5.1M overtime cut).

## Candidate strengths to emphasize when tailoring

- Executive leadership: Assistant Deputy Director of Prisons (SC DOC), former
  Complex Warden / Senior Deputy Regional Director, Federal Bureau of Prisons
- Managed budgets exceeding $950M; large-scale organizational design
- Built and executed leadership & talent management programs across multiple
  facilities (improved performance, retention, morale)
- Crisis management / emergency preparedness (Chief, Office of Emergency
  Preparedness; ICS-100; interagency disaster coordination)
- Remote workforce management & communication
- Wellness credibility: wellness coaching, competitive powerlifter, martial
  artist, motivational interviewing, curriculum development
- Secret clearance

## Workflow (what the daily run does)

1. Read this config + `seen-jobs.md` for already-reported jobs.
2. Run the search queries above via the Indeed tools (rotate/vary phrasing).
3. Filter to criteria; skip anything already in `seen-jobs.md`.
4. For strong fits, pull full job details, and tailor the base résumé
   (`base-resume.md`) to the posting — reorder/reword the summary and skills
   to mirror the job description, keeping all facts truthful.
5. Create a Gmail **draft** digest to the owner: each job with company,
   salary, location, the APPLY LINK, and the tailored résumé text ready to
   paste in.
6. Append reported jobs to `seen-jobs.md`, commit, push.

Note: applications cannot be auto-submitted (Indeed tools provide apply
links only) — the owner clicks the apply link and pastes the tailored résumé.
