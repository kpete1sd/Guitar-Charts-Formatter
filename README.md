# 🎸 Gig Chart Formatter

A Streamlit app that turns song charts and guitar tabs in **any format** (PDF, Word, text, ChordPro,
RTF, web pages, photos or scans), one at a time or as a batch, into one clean layout that's easy to read
on an iPad at a gig:

1. **Song title** (and artist)
2. **Key** and **BPM** (plus time signature, capo and tuning when known)
3. **Band notes** you've saved for the song
4. **Song sections** (Intro, Verse, Chorus…) with **chords above lyrics**
5. A **YouTube link** to the song at the end

## Running it on Windows

1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Double-click **`run_app.bat`**. The first run installs everything (takes a few minutes); after that it starts straight away.
   Your browser opens to the app at http://localhost:8501.

Or from a terminal: `pip install -r requirements.txt` then `streamlit run app.py`.

### Optional extras
- **Claude AI converter (recommended).** This is the most accurate option for photos, scans and messy layouts, and it can estimate BPM
  when the chart doesn't give one. Paste an Anthropic API key in the sidebar, or copy
  `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and put the key there.
- **Tesseract OCR** reads photos and scans *without* Claude. On Windows, install it from
  https://github.com/UB-Mannheim/tesseract/wiki (the app finds it automatically in Program Files).
- **YouTube Data API key**: with this, links go straight to the top video. Without it, each link opens a YouTube
  search for the song.

## Deploying to Streamlit Community Cloud
Push this folder to GitHub, create the app with `app.py` as the entry point, and paste your keys into
**Settings → Secrets** (same names as in `secrets.toml.example`). `packages.txt` installs Tesseract there.
The cloud server forgets its files when it restarts, so use **Back up notes (.json)** in the sidebar now and then
and **Restore / merge notes** to bring them back.

## Photos and scans
Charts can come in as phone photos (JPG, PNG, HEIC), screenshots, scanned PDFs, multi-page TIFFs from a
document scanner, PDFs that mix typed and scanned pages, or a Word file with the chart pasted in as a picture.

- **Automatic clean-up** before reading: turns sideways or upside-down pages upright, straightens tilt,
  evens out shadows and lamp light, removes the desk or music stand around the page, and flips dark-mode
  screenshots (light text on black).
- **Chords stay in place.** OCR keeps each word's position, so chords land above the right syllable, and
  common misreads (`8b`→`Bb`, `Cc`→`C`, `Am/`→`Am7`) are fixed on chord lines only, never in lyrics.
- **Several photos of one song:** select them together and tick *"The photos/scans are pages of ONE song"*.
  They're joined in file-name order (`page1`, `page2`, … or the camera's own numbering).
- **Mixed PDFs:** typed pages are read as text, scanned pages are read from the picture, and everything
  stays in page order.
- **Long phone screenshots** are cut into overlapping strips for Claude so the text isn't shrunk.
- **Check it:** the *Edit chart* tab has *Compare with the original* to show the cleaned-up page next to
  the converted text, and the message after converting gives the OCR quality.

Claude AI mode gives the best results on photos and also reads handwritten chords and band markings.
Built-in mode needs Tesseract (see above) and works best on printed charts.

## Stage mode (sidebar switch, on by default)
Built for reading at a glance from a music stand in a dim, glare-prone room:
- **Big, legible type** in Atkinson Hyperlegible (bundled, so it works without internet). Sharps and flats use real ♯/♭ symbols.
- **iPad page size** (3:4) for PDFs, so the chart fills the screen with no paper margins. Letter and A4 are still available.
- **Dark PDF option**: true black background with off-white text (less glare, less light on your face).
- **Boxed chords** that stand out by weight, size and an outlined box, not just colour, so they stay readable under red/blue stage lights.
- **Road map** under the title (`V1 · Ch · V2 · Ch · Solo · Br · Ch ×2 · Outro`), colour-matched to the sections.
- **Colour-coded sections**: blue verse, teal pre-chorus, magenta shaded chorus, green bridge, orange solo, grey intro/outro.
- **Keep-screen-awake** (☀ button in the HTML version) and a toolbar that fades out while you play.
  Safari only allows keep-awake for pages opened from a web address. For PDFs, or HTML opened from the Files app,
  set *Settings → Display & Brightness → Auto-Lock → Never* before the gig.

Switch Stage mode off to compare with the classic look. The **Preview** tab can show either the screen (HTML) version or the actual PDF pages.

## Outputs
| Format | Best for |
|---|---|
| **PDF** | forScore, OnSong, MobileSheets, the Files app. Auto-shrinks to one page when it's close. |
| **HTML** | Safari: A−/A+ text size, ◫ columns (landscape), ◐ dark stage mode, ▶ auto-scroll |
| **ChordPro (.cho)** | Importing into OnSong / SongbookPro as an editable, transposable song |
| **Set list PDF / HTML / ZIP** | All converted songs in the order you choose, one song per page |

## Chart text format (what you edit in the app)
```
[Verse 1]
A-8                 Bm-8
No matter what you are, I will always be with you
> Band stops on the 4
[Solo]
|A-4| Bm-4| D-4| E-4|
```
- `[Section]` labels go on their own line.
- A chord line placed directly above a lyric line becomes a chord/lyric pair.
- Lines starting with `> ` are cue notes.
- Beat counts such as `A-4` are kept and shown in small type next to the chord.

Transposing (in the Edit tab) changes every chord and the key, and keeps the spelling right for the new key
(flats in F, B♭, E♭…).

## Files
- `app.py`: the Streamlit app
- `chartlib/vision.py`: photo and scan clean-up, and position-keeping OCR
- `chartlib/`: extraction, parsing (built-in and Claude), key detection and transposition, plus the HTML, PDF and ChordPro renderers
- `chartlib/stage.py` + `chartlib/fonts/`: Stage mode (section colours, road map, Atkinson Hyperlegible under the SIL Open Font License, and a tiny DejaVu-based ♯/♭ symbol font)
- `data/band_notes.json`: your saved band notes, created on first save
