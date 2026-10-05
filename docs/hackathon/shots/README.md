# Real application screenshots

These PNGs show the installed InspirationSpace application's real frontend and FastAPI backend, running locally with a separate demonstration database. The interface language is set to English. User inputs were written for the demonstration; AI analysis, discussion replies, translations, and generated titles came from live model calls. Two views were accepted through the application's adoption endpoint.

Screenshots were captured at **1600 × 1000** in a separate Chromium browser connected to `http://127.0.0.1:8000`. They are unedited captures of the running application, with no fabricated interface or substituted AI output. The analysis and discussion shots show the first view before adoption; the home and Anthology shots show the later state after adoption.

| File | Suggested English caption |
|---|---|
| `01-home.png` | Capture inspirations and see their titles and workflow stages. |
| `02-whetstone.png` | Examine a view with reasons to adopt it, its strongest counterargument, and classification suggestions. |
| `02b-whetstone-discussion.png` | Discuss the scope of a claim and respond to AI questions before deciding whether to adopt it. |
| `03-anthology.png` | Browse user-accepted views with filters, classifications, and bilingual titles. |
| `04-login.png` | Sign in to a local account with the interface set to English. |
| `05-distillation.png` | Explore an observation through AI questions before moving into polishing. |

For the Devpost gallery, place `02-whetstone.png` first, then the home, discussion, Anthology, and distillation shots. Add the login shot last. Review the full-size images before uploading.

## Capture notes

The requested `desktop_browser` tool was unavailable, and the available desktop tool could not read the dedicated application window. A separate browser captured the same locally served application instead. No existing personal browser profile was used.

Some built-in provider preset labels remain Chinese even with English selected, and native date inputs use the system locale. The Anthology header also truncates part of its slogan at this viewport. These are the application's current rendered appearance; the captures preserve it without changing application code.
