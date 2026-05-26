# Conductor — Setup Tutorial Script
> Use this to record the 2 tutorial clips shown to users after install.
> Each clip is short, focused, no talking needed — screen recording with captions.

---

## Clip 1 — Ableton Control Surface Setup
**Length:** ~45 seconds
**When shown:** After install.command finishes

---

### What to record on screen

**Scene 1 — Open Ableton Live** *(3 sec)*
- Show Ableton opening from Dock
- Caption: *"Open Ableton Live"*

---

**Scene 2 — Open Preferences** *(4 sec)*
- Click `Ableton Live` in menu bar → `Preferences`
- OR press `Cmd + ,`
- Caption: *"Open Preferences  ( Cmd + , )"*

---

**Scene 3 — Go to MIDI tab** *(3 sec)*
- Click the `Link / Tempo / MIDI` tab (left sidebar in Preferences)
- Caption: *"Click  Link / Tempo / MIDI"*

---

**Scene 4 — Set Control Surface 1** *(6 sec)*
- Find the `Control Surface` row — first dropdown (slot 1)
- Click it → scroll down → select `Ableton_Live_MCP`
- Caption: *"Control Surface 1 → Ableton_Live_MCP"*

---

**Scene 5 — Set Control Surface 2** *(6 sec)*
- Find the second `Control Surface` row (slot 2)
- Click it → select `AbletonOSC`
- Caption: *"Control Surface 2 → AbletonOSC"*

---

**Scene 6 — Close and restart Ableton** *(5 sec)*
- Close the Preferences window
- Quit Ableton → reopen it
- Caption: *"Restart Ableton to apply"*

---

**Scene 7 — Done confirmation** *(3 sec)*
- Show Ableton open with a session loaded
- Caption: *"Ableton is now connected to Conductor ✓"*

---

### Captions summary (in order)
```
1. Open Ableton Live
2. Open Preferences  ( Cmd + , )
3. Click  Link / Tempo / MIDI
4. Control Surface 1  →  Ableton_Live_MCP
5. Control Surface 2  →  AbletonOSC
6. Restart Ableton to apply
7. Ableton is now connected to Conductor ✓
```

---
---

## Clip 2 — Connect Your NotebookLM Knowledge Base
**Length:** ~60 seconds
**When shown:** After Ableton setup, or from inside Conductor settings

---

### What is NotebookLM?
> NotebookLM is a free Google tool. You upload your own documents — mixing guides,
> music theory notes, plugin manuals, anything. Conductor will query it when you ask
> production questions. Your knowledge base, always available.

---

### What to record on screen

**Scene 1 — Open notebooklm.google.com** *(4 sec)*
- Open Chrome → go to `notebooklm.google.com`
- Caption: *"Go to notebooklm.google.com"*

---

**Scene 2 — Create a new notebook** *(5 sec)*
- Click `+ New Notebook`
- Give it a name e.g. *"Music Production"*
- Caption: *"Create a new notebook"*

---

**Scene 3 — Add your sources** *(8 sec)*
- Click `+ Add Source`
- Upload a PDF or paste a link (show dragging a PDF file in)
- Caption: *"Add your sources — PDFs, docs, links, anything"*

---

**Scene 4 — Copy the notebook ID** *(8 sec)*
- Look at the browser URL bar
- URL looks like: `notebooklm.google.com/notebooklm#?authuser=0&nb=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- Highlight and copy the long ID at the end
- Caption: *"Copy the notebook ID from the URL"*

---

**Scene 5 — Open Terminal** *(4 sec)*
- Open Terminal (Spotlight → Terminal)
- Caption: *"Open Terminal"*

---

**Scene 6 — Run the connect command** *(8 sec)*
- Type: `notebooklm use <paste-your-id-here>`
- Press Enter
- Show success output
- Caption: *"notebooklm use  < your notebook ID >"*

---

**Scene 7 — Test it in Conductor** *(10 sec)*
- Open `app/index.html` in Chrome
- Click the source button → select `NotebookLM`
- Type: *"What's a good way to EQ a kick drum?"*
- Show the N badge response appear
- Caption: *"Ask anything — Conductor queries your knowledge base"*

---

**Scene 8 — Done** *(3 sec)*
- Caption: *"Your knowledge base is connected ✓"*

---

### Captions summary (in order)
```
1. Go to notebooklm.google.com
2. Create a new notebook
3. Add your sources — PDFs, docs, links, anything
4. Copy the notebook ID from the URL
5. Open Terminal
6. notebooklm use  <your-notebook-id>
7. Ask anything — Conductor queries your knowledge base
8. Your knowledge base is connected ✓
```

---
---

## Recording Notes

| | |
|---|---|
| **Screen resolution** | 1920×1080 or Retina 2x — crop to just the relevant window |
| **Cursor** | Make cursor large and visible (System Settings → Accessibility → Pointer) |
| **Speed** | Record at normal speed, no need to speed up — keep it readable |
| **Audio** | No voiceover needed — captions only. Add subtle background music if wanted |
| **Format** | Export as MP4, max 720p for web embedding |
| **Tool** | QuickTime Player → New Screen Recording (free, built into macOS) |

---

## Where These Clips Get Used

| Clip | Where shown |
|---|---|
| Clip 1 — Ableton setup | End screen of `install.command` → "Watch setup video" link |
| Clip 2 — NotebookLM | Conductor settings page → Integrations → NotebookLM row → "How to connect" |
| Both | README / landing page when app is released |
