# Transit Reliability & Equity: scenario dashboard (v9)

A human-in-the-loop dashboard for bus disruptions, built on the **v9 notebook**
(`notebooks/Transit_Agentic_AI_Submission_v9.ipynb`). **AI agents sense, organize and explain; fixed, published rules
score; people decide.** It runs the notebook's **14 scenarios** (the Section B sample and the 13 presets) through role
views for the team. Every scenario is **synthetic**; outcomes are labelled **SIMULATED**; nothing is dispatched.

## The team (sidebar, Step 1)

| Role | Person | What they do |
|---|---|---|
| 🎧 Dispatcher (1st reviewer) | **Ariyan** | Opens a scenario, reads the review screen and approves, revises or rejects |
| 🧭 Supervisor (2nd reviewer) | **Terri-Ann** | Independently approves or rejects **high-impact** actions (second bus, accessible van, high priority) |
| 🛠️ Operations Officer | **Grant** | Carries out the approved action, alerts the driver and records the result |
| 🚌 Bus Driver | **Habib** | Reads alerts on the driver screen and acknowledges them |

Ariyan, Terri-Ann, Grant and Habib are added to the ethics-training roster as fully trained (2026-11-16). The notebook's
**sample reviewers stay on the roster**, so you can type their names to show the safeguards:

| Name | What happens |
|---|---|
| Farah Haddad | Blocked: ethics refresher overdue |
| Eli Turner | Blocked: missing two courses |
| Gabe Ortiz | Must recuse from a Depot B dispatch (conflict of interest) |
| Ana Lopez, Chen Wei | Trained sample reviewers |

## Running a scenario (about 3 minutes)

1. **Ariyan:** on **✅ My task**, open **▶ Open a new scenario**, pick one and press **▶ Process case**. Read *What
   happened*, choose an option yourself (nothing is preselected), tick the checklist, write a reason (15+ characters)
   and press **Submit as Ariyan**.
2. **Terri-Ann** (only if the action is high-impact): pick her in Step 1. Her case opens automatically. Approve or reject.
3. **Grant:** check the driver message, pick **Completed** and press **Record result and alert the driver**. The Outcome
   Evaluator runs at once (SIMULATED).
4. **Habib:** read the alert on the driver screen and press **👍 Acknowledge**.

The **tracker** at the top shows who is up next (👉). **↻ Refresh** in the sidebar shows what others have done.
Each person can use their own laptop or phone on the same link; everyone sees the same cases.

### Suggested scenarios for the presentation

| Scenario | What it shows |
|---|---|
| Section B sample · Route 12 cancellation | Full path: Ariyan approves a second bus → Terri-Ann → Grant → Habib; "What happened" names the wheelchair user left at Elm Ave |
| Accessibility · Full bus, no room for a wheelchair… | Driver alert is *drafted* until both approve, then sent: skip boarding, accessible vehicle requested |
| Accessibility · Wheelchair and strollers waiting, room on board | No review needed: the ramp alert goes straight to Habib |
| Conflicting data · R3 vehicle feed vs. public reports | Operator check before anything is scored |
| Uncorroborated social report only · R4 | Continue monitoring; close as a false alarm |
| Agent error · Vision Agent fails twice | Safe mode / safe default |

Safeguards to show on any review: submit with no option (refused), a short reason (refused, text kept), *Farah Haddad*
as reviewer (blocked), the same name as both reviewers (refused), **Revise** with an option excluded (re-ranked), and
**Simulate: deadline passes** (Safe Default).

## Deploy on Streamlit Community Cloud

1. On <https://share.streamlit.io>, choose **Create app → Deploy a public app from GitHub**.
2. Pick this repository, branch **main**, main file **`app_streamlit.py`**.
3. Under **Advanced settings**, choose **Python 3.12** and paste your Secrets (below). Then **Deploy**.
   The first start takes a few minutes while packages install.

### Secrets (all optional)

Template: `.streamlit/secrets.toml.example`. Format: `NAME = "value"`, one per line.

| Secret | Default | What it does |
|---|---|---|
| `DASHBOARD_PASSWORD` | none | Asks for a password before the dashboard opens (recommended if you share the link) |
| `OPENAI_API_KEY` (or `OPENROUTER_API_KEY`) | none | Live LLM explanations; otherwise the notebook's template text |
| `DISPATCHER_NAME`, `SUPERVISOR_NAME`, `OFFICER_NAME`, `DRIVER_NAME` | Ariyan, Terri-Ann, Grant, Habib | Names in Step 1 |
| `REQUIRE_SUPERVISOR_APPROVAL` | "0" | "1": Terri-Ann approves every action. "0": only high-impact actions, as in the notebook |
| `DEMO_DEADLINE_SCALE` | "1.0" | Review deadlines (5 / 10 / 20 min) × this number |
| `CARTO_API_KEY` | none | CARTO street map; otherwise OpenStreetMap |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `DRIVER_PHONE_NUMBER` | none | Also text driver alerts; otherwise driver screen only |

## Good to know

- **Shared state:** all cases live in the app's memory and are shared by everyone. They are cleared when the app
  restarts (after a redeploy, or when Streamlit Cloud puts an idle app to sleep). **Records → Cases → Reset the demo**
  clears them on purpose.
- **Deadlines are real.** If nobody completes a review in time, the case goes to the Safe Default. That's by design.
- **Scenario mode only:** no NJ Transit login, camera model or FLAN-T5 is used. The map shows the notebook's synthetic
  network over a Newark basemap.

## Files

| File | Purpose |
|---|---|
| `app_streamlit.py` | The dashboard (Streamlit main file) |
| `team.py` | The team and roster, scenario list, driver alerts, tracker |
| `transit_ai/` | The v9 notebook's code, one file per section, run in notebook order (generated; do not edit by hand) |
| `notebooks/` | The v9 notebook (source of truth) |
| `tools/build_from_notebook.py` | Regenerates `transit_ai/` from the notebook |
| `tools/rehearse.py` | Clicks through every role and scenario path and checks the results |

After editing the notebook: `python tools/build_from_notebook.py notebooks/Transit_Agentic_AI_Submission_v9.ipynb .`

Run locally: `pip install -r requirements.txt` then `streamlit run app_streamlit.py`.
