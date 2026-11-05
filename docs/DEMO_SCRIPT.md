# Demo video script (2 minutes)

Owner: Aditya. Deepak records the video.

## Before recording
- Fresh DB: stop the server, delete `sutradhar.db*`, start the server again.
- Have three windows open: the **browser** (frontend), the **terminal** (backend server) and the **phone** (Telegram, mirrored or on camera).
- Keep Google Calendar open in a separate tab.
- The teammate playing the expert must have sent `/start` to `@aditya1267_bot`.
- Record backup clips of the eval page and of kill/resume in advance, in case something breaks live.

## Script

| Time | On screen | Voiceover |
|---|---|---|
| 0:00–0:10 | Title / frontend home | "Expert networks like GLG charge thousands to book one call. Sutradhar does the whole job: request in, booked call out." |
| 0:10–0:30 | Type into the request box: *"kal shaam 6 se 8 ke beech kisi warehouse chalane wale se 20 minute baat karni hai, 2k tak de sakta hoon"*, then Submit | "A request it has never seen, in Hinglish. The LLM only parses it. Code validates the hard constraints: 20 min, 6–8 PM, max ₹2,000." |
| 0:30–0:55 | Zoom into the shortlist: 🟢 verified, 🟡 unverifiable, 🔴 contradicted | "Every expert's claims are checked against Crustdata Person Enrich, with the source cited. This one claims 'Warehouse Head', but Crustdata shows only an internship, so he's dropped. This one charges ₹2,500, over budget, so he's skipped." |
| 0:55–1:20 | The phone buzzes. The teammate replies **"7:15 for 1800"**. The timeline updates, then **BOOKED** | "The top verified expert gets a Telegram message. He replies in plain text. The LLM parses it, code checks it's inside the window and under budget, and books it." |
| 1:20–1:30 | Google Calendar tab: show the event | "The invite lands on both calendars: 7:15 PM, ₹1,800." |
| 1:30–1:45 | Submit a second request. As soon as the expert is messaged, **Ctrl+C in the terminal**, restart the server, show the timeline | "Kill it mid-run. It restarts from SQLite exactly where it stopped. The expert did not get a second message, because every send and every invite has an idempotency key." |
| 1:45–1:58 | Eval page with the big numbers | "60 runs, 20 requests in 3 paraphrases each: 0 budget violations, 0 time violations, 0 double bookings, every planted fake caught." (**Only say this if the real eval produced these numbers.**) |
| 1:58–2:00 | Logo | "Sutradhar. The one who coordinates." |

## Notes
- Killing the process exactly between the calendar insert and the status save is hard to time live.
  The reliable live demo is: kill right after the expert is messaged, restart, and show that no second message went out.
  The calendar case (`already_exists`) was proven in testing; show that terminal log or a screenshot as a cut-in.
- Read the eval numbers from `GET /eval/latest` on the day. Never use the fixture numbers in the video.
