"""Gig Chart Formatter - turn any chart or tab into a clean iPad gig chart.

Run:  streamlit run app.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from chartlib.ai import DEFAULT_MODEL, ai_parse
from chartlib.chordpro import to_chordpro
from chartlib.extract import SUPPORTED_EXT, extract, ocr_images, tesseract_available
from chartlib.model import NOTE_FIELDS, NotesStore, song_slug, youtube_lookup, youtube_search_url
from chartlib.parse import heuristic_parse
from chartlib.render_html import render_html, song_meta
from chartlib.render_pdf import render_pdf

APP_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_PATH = os.path.join(APP_DIR, "data", "band_notes.json")

st.set_page_config(page_title="Gig Chart Formatter", page_icon="🎸", layout="wide")


# ------------------------------------------------------------------ helpers
def secret(name: str) -> str:
    try:
        v = st.secrets.get(name)
        if v:
            return str(v)
    except Exception:
        pass
    return os.environ.get(name, "")


@st.cache_resource
def notes_store() -> NotesStore:
    return NotesStore(NOTES_PATH)


@st.cache_data(show_spinner=False, max_entries=400)
def _html(payload: str, notes_position: str, stage: bool = False) -> str:
    items = json.loads(payload)
    return render_html([(s, n) for s, n in items], notes_position, stage=stage)


@st.cache_data(show_spinner=False, max_entries=400)
def _pdf(payload: str, page: str, notes_position: str, fit: bool, stage: bool = False, dark: bool = False) -> bytes:
    items = json.loads(payload)
    return render_pdf([(s, n) for s, n in items], page, notes_position, fit, stage=stage, dark=dark)


@st.cache_data(show_spinner=False, max_entries=200)
def _pdf_pages_png(pdf: bytes, scale: float = 1.3):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    out = []
    for i in range(len(doc)):
        buf = io.BytesIO()
        doc[i].render(scale=scale).to_pil().save(buf, format="PNG")
        out.append(buf.getvalue())
    return out


def payload(items) -> str:
    return json.dumps(items, sort_keys=True, default=str)


def safe_name(title: str) -> str:
    return re.sub(r"[^\w\- ]+", "", title or "chart").strip().replace(" ", "_") or "chart"


SONG_DEFAULTS = {"title": "Untitled", "artist": "", "key": "", "key_source": "", "bpm": None,
                 "bpm_source": None, "time_signature": "", "capo": "", "tuning": "", "youtube_url": "",
                 "chart": "", "transpose": 0}

ss = st.session_state
ss.setdefault("songs", {})      # sid -> song dict
ss.setdefault("order", [])      # sids in upload order
ss.setdefault("log", [])


def add_song(sid: str, song: dict):
    full = {**SONG_DEFAULTS, **{k: v for k, v in song.items() if v not in (None, "") or k == "bpm"}}
    full["bpm"] = song.get("bpm") or None
    ss.songs[sid] = full
    if sid not in ss.order:
        ss.order.append(sid)


def convert(name: str, data: bytes, use_ai: bool, api_key: str, model: str, yt_key: str):
    msgs = []
    ex = extract(name, data)
    msgs += ex.warnings
    song, engine = None, "built-in"
    if use_ai and api_key and (ex.text.strip() or ex.images or ex.pdf_bytes):
        try:
            song = ai_parse(ex, api_key, model)
            engine = "Claude"
        except Exception as e:
            msgs.append(f"Claude couldn't convert this one ({type(e).__name__}: {str(e)[:160]}); "
                        "used the built-in converter instead.")
    if song is None:
        if ex.needs_ocr or (not ex.text.strip() and ex.images):
            if tesseract_available():
                ex.text = ocr_images(ex.images)
                msgs.append("Photo/scan read with OCR - check chords carefully (Claude AI mode is more accurate).")
            else:
                msgs.append("This is a photo or scan. Turn on Claude AI mode (or install Tesseract OCR) to read it.")
        if not ex.text.strip():
            return None, msgs
        song = heuristic_parse(ex.text, name)
    song["source"] = name
    song["engine"] = engine
    if not song.get("youtube_url") and yt_key:
        found = youtube_lookup(song.get("title", ""), song.get("artist", ""), yt_key)
        if found:
            song["youtube_url"] = found
    return song, msgs


# ------------------------------------------------------------------ sidebar
store = notes_store()
with st.sidebar:
    st.header("⚙️ Settings")
    default_key = secret("ANTHROPIC_API_KEY")
    engine = st.radio("Converter", ["Claude AI (most accurate)", "Built-in (offline, free)"],
                      index=0 if default_key else 1,
                      help="Claude reads photos, scans and messy layouts and can estimate BPM. "
                           "The built-in converter works offline on text-based files.")
    use_ai = engine.startswith("Claude")
    api_key = ""
    if use_ai:
        api_key = st.text_input("Anthropic API key", value=default_key, type="password",
                                help="Get one at console.anthropic.com. Or put ANTHROPIC_API_KEY in "
                                     ".streamlit/secrets.toml so you never have to paste it.")
        if not api_key:
            st.warning("Add an API key, or switch to Built-in.")
    with st.expander("Advanced"):
        model = st.text_input("Claude model", value=secret("CLAUDE_MODEL") or DEFAULT_MODEL)
        yt_key = st.text_input("YouTube Data API key (optional)", value=secret("YOUTUBE_API_KEY"),
                               type="password",
                               help="With a key, each chart links straight to the top video. "
                                    "Without one, the link opens a YouTube search for the song.")
        st.caption("OCR for photos (built-in mode): " +
                   ("✅ Tesseract found" if tesseract_available() else "❌ Tesseract not installed"))

    st.subheader("📄 Output")
    stage = st.toggle("🎤 Stage mode", value=True,
                      help="Built for reading on stage: bigger Atkinson Hyperlegible type, iPad-shaped pages, "
                           "boxed chords that stay readable under coloured lights, a road map of the song, "
                           "colour-coded sections and keep-screen-awake. Turn off to see the classic look.")
    page = st.selectbox("PDF page size", ["iPad", "Letter", "A4"], index=0 if stage else 1,
                        help="'iPad' is a 3:4 page that fills the iPad screen with no paper margins.")
    dark = st.checkbox("Dark PDF (black background)", value=stage,
                       help="Less glare and less light on your face on a dark stage. The HTML version has "
                            "its own light/dark button.")
    notes_position = st.radio("Band notes go", ["top", "bottom"], horizontal=True,
                              format_func=lambda x: "Under the title" if x == "top" else "At the end")
    fit = st.checkbox("Shrink text to fit one page when close", value=True)

    st.subheader("📝 Band notes library")
    st.caption(f"{len(store.data)} song(s) with saved notes. Notes reload automatically "
               "whenever you convert a song with the same title.")
    st.download_button("Back up notes (.json)", json.dumps(store.data, indent=2, ensure_ascii=False),
                       file_name="band_notes.json", mime="application/json")
    up_notes = st.file_uploader("Restore / merge notes (.json)", type=["json"], key="notes_up")
    if up_notes is not None and st.button("Merge these notes"):
        try:
            store.merge(json.load(up_notes))
            st.success("Notes merged.")
        except Exception as e:
            st.error(f"Couldn't read that file: {e}")

    st.divider()
    if ss.order and st.button("🗑️ Clear all songs"):
        ss.songs, ss.order = {}, []
        st.rerun()


# ------------------------------------------------------------------ main
st.title("🎸 Gig Chart Formatter")

tab_up, tab_paste, tab_help = st.tabs(["📂 Upload charts", "📋 Paste a chart", "❓ Using it on the iPad"])
with tab_up:
    files = st.file_uploader("Charts or tabs (select many for a batch)", accept_multiple_files=True,
                             type=[e.lstrip(".") for e in SUPPORTED_EXT] + ["doc"])
    new = []
    for f in files or []:
        data = f.getvalue()
        sid = hashlib.sha1(f.name.encode() + data).hexdigest()[:12]
        if sid not in ss.songs:
            new.append((sid, f.name, data))
    label = f"Convert {len(new)} new file{'s' if len(new) != 1 else ''}" if new else "Convert"
    if st.button(label, type="primary", disabled=not new or (use_ai and not api_key)):
        prog = st.progress(0.0, text="Converting…")
        for i, (sid, name, data) in enumerate(new):
            prog.progress(i / len(new), text=f"Converting {name} ({i + 1}/{len(new)})…")
            song, msgs = convert(name, data, use_ai, api_key, model, yt_key)
            for m in msgs:
                ss.log.append((name, m))
            if song:
                add_song(sid, song)
            else:
                ss.log.append((name, "Nothing readable found in this file."))
        prog.progress(1.0, text="Done")
        st.rerun()

with tab_paste:
    with st.form("paste_form", clear_on_submit=True):
        p_title = st.text_input("Song title (optional - taken from the chart if blank)")
        p_text = st.text_area("Paste chart text (Ultimate Guitar, email, ChordPro…)", height=260)
        if st.form_submit_button("Convert pasted chart", type="primary") and p_text.strip():
            sid = hashlib.sha1(p_text.encode()).hexdigest()[:12]
            from chartlib.extract import Extracted
            ex = Extracted(filename=(p_title or "pasted") + ".txt", kind="text", text=p_text)
            song = None
            if use_ai and api_key:
                try:
                    song = ai_parse(ex, api_key, model)
                    song["engine"] = "Claude"
                except Exception as e:
                    ss.log.append(("pasted chart", f"Claude failed ({e}); used built-in converter."))
            if song is None:
                song = heuristic_parse(p_text, ex.filename)
                song["engine"] = "built-in"
            if p_title:
                song["title"] = p_title
            song["source"] = "pasted text"
            add_song(sid, song)
            st.rerun()

with tab_help:
    st.markdown("""
**Getting charts onto the iPad**
- **PDF** - best for forScore, OnSong, MobileSheets or the Files app. AirDrop it, or save it to iCloud Drive / Google Drive.
- **HTML** - open in Safari for a live chart: **A− / A+** resize text, **◫** switches to columns (great in landscape),
  **◐** toggles light/dark, **☀** keeps the screen awake (lit = on), **▶** starts auto-scroll (tap again for faster,
  4th tap stops). In Stage mode the buttons fade after a few seconds; touch the screen to bring them back.
  The YouTube link is a real tappable link.
- **Stage mode** (sidebar switch, on by default): big Atkinson Hyperlegible type, boxed chords with ♭/♯ symbols, a road map
  of the song under the title, and colour-coded sections (blue verse, magenta shaded chorus, green bridge, orange solo).
  PDFs use an iPad-shaped page and can be black-background. Turn it off to compare with the classic look.
- **Keep-awake tip:** Safari can only keep the screen on for pages opened from a web address. For PDFs, or HTML opened from
  the Files app, set **Settings → Display & Brightness → Auto-Lock → Never** before the gig.
- **ChordPro (.cho)** - imports into OnSong / SongbookPro / forScore as an editable, transposable song.
- **Set list ZIP / PDF** - everything converted, in the order you set, with each song starting on a new page.

**Editing the chart text** - section labels in square brackets (`[Chorus]`), chords on their own line directly above the
lyric they go with, and cue notes on lines starting with `> `. Beat counts like `A-4` are kept and shown small.
""")

for name, m in ss.log[-8:]:
    st.info(f"**{name}** - {m}")
if ss.log and st.button("Dismiss messages"):
    ss.log = []
    st.rerun()

if not ss.order:
    st.stop()

st.divider()
st.subheader(f"Your charts ({len(ss.order)})")

for sid in list(ss.order):
    song = ss.songs[sid]
    notes = store.get(song["title"])
    key, n = song_meta(song)
    head = f"**{song['title']}**" + (f" — {song['artist']}" if song.get("artist") else "") + \
           f"  ·  Key {key or '?'}  ·  {song.get('bpm') or '?'} BPM" + ("  ·  📝" if notes else "")
    with st.expander(head, expanded=len(ss.order) == 1 or ss.get("active") == sid):
        t_prev, t_edit, t_notes, t_dl = st.tabs(["👀 Preview", "✏️ Edit chart", "📝 Band notes", "⬇️ Download"])
        item = [[song, notes]]

        with t_prev:
            view = st.radio("Preview", ["Screen (HTML)", "PDF pages"], horizontal=True, key=f"view_{sid}",
                            label_visibility="collapsed")
            if view.startswith("Screen"):
                components.html(_html(payload(item), notes_position, stage), height=860, scrolling=True)
            else:
                pngs = _pdf_pages_png(_pdf(payload(item), page, notes_position, fit, stage, dark))
                cols = st.columns(min(len(pngs), 2))
                for i, png in enumerate(pngs):
                    cols[i % len(cols)].image(png, caption=f"Page {i + 1} of {len(pngs)}")

        with t_edit:
            flags = []
            if song.get("key_source") == "detected":
                flags.append("key was worked out from the chords")
            if song.get("bpm_source") == "estimate":
                flags.append("BPM is Claude's estimate of the original recording")
            if not song.get("bpm"):
                flags.append("no BPM on the chart - add it below")
            if flags:
                st.caption("⚠️ Please check: " + "; ".join(flags) + ".")
            st.caption(f"Source: {song.get('source', '')} · converted with {song.get('engine', '')}")
            with st.form(f"edit_{sid}"):
                c1, c2 = st.columns(2)
                title = c1.text_input("Title", song["title"])
                artist = c2.text_input("Artist", song.get("artist", ""))
                c1, c2, c3, c4, c5 = st.columns(5)
                k = c1.text_input("Key (as written)", song.get("key", ""))
                bpm = c2.text_input("BPM", str(song.get("bpm") or ""))
                tsig = c3.text_input("Time sig.", song.get("time_signature", ""))
                capo = c4.text_input("Capo", song.get("capo", ""))
                tuning = c5.text_input("Tuning", song.get("tuning", ""))
                c1, c2 = st.columns([3, 1])
                yt = c1.text_input("YouTube link (blank = automatic search link)", song.get("youtube_url", ""),
                                   placeholder=youtube_search_url(song["title"], song.get("artist", "")))
                tr = c2.number_input("Transpose (semitones)", -11, 11, int(song.get("transpose") or 0))
                chart = st.text_area("Chart", song.get("chart", ""), height=480,
                                     help="[Section] labels, chord line directly above its lyric line, "
                                          "'> ' for cue notes.")
                if st.form_submit_button("Save changes", type="primary"):
                    old_title, old_key = song["title"], song.get("key") or ""
                    m = re.search(r"\d{2,3}", bpm or "")
                    song.update(title=title.strip() or "Untitled", artist=artist.strip(), key=k.strip(),
                                bpm=int(m.group()) if m else None, time_signature=tsig.strip(),
                                capo=capo.strip(), tuning=tuning.strip(), youtube_url=yt.strip(),
                                transpose=int(tr), chart=chart)
                    if k.strip() != old_key:
                        song["key_source"] = "chart"
                    if m:
                        song["bpm_source"] = "chart"
                    if song_slug(old_title) != song_slug(song["title"]) and store.get(old_title) \
                            and not store.get(song["title"]):
                        store.put(song["title"], store.get(old_title))
                    ss.songs[sid] = song
                    ss.active = sid
                    st.rerun()

        with t_notes:
            st.caption("Saved notes print on this song's chart and come back automatically next time "
                       "you convert a song with this title.")
            with st.form(f"notes_{sid}"):
                vals = {}
                c1, c2 = st.columns(2)
                for i, (fk, lbl) in enumerate(NOTE_FIELDS):
                    if fk == "other":
                        vals[fk] = st.text_area(lbl, notes.get(fk, ""), height=110)
                    else:
                        vals[fk] = (c1 if i % 2 == 0 else c2).text_input(lbl, notes.get(fk, ""))
                if st.form_submit_button("Save band notes", type="primary"):
                    store.put(song["title"], vals)
                    ss.active = sid
                    st.rerun()

        with t_dl:
            fn = safe_name(song["title"])
            c1, c2, c3, c4 = st.columns(4)
            c1.download_button("📄 PDF", _pdf(payload(item), page, notes_position, fit, stage, dark),
                               file_name=f"{fn}.pdf", mime="application/pdf", key=f"pdf_{sid}")
            c2.download_button("🌐 HTML (Safari)", _html(payload(item), notes_position, stage),
                               file_name=f"{fn}.html", mime="text/html", key=f"html_{sid}")
            c3.download_button("🎼 ChordPro", to_chordpro(song, notes), file_name=f"{fn}.cho",
                               mime="text/plain", key=f"cho_{sid}")
            if c4.button("Remove", key=f"rm_{sid}"):
                ss.order.remove(sid)
                ss.songs.pop(sid, None)
                st.rerun()

# ------------------------------------------------------------------ batch / set list
st.divider()
st.subheader("🎤 Set list & batch download")
df = pd.DataFrame([{"Order": i + 1, "Title": ss.songs[s]["title"], "Key": song_meta(ss.songs[s])[0],
                    "BPM": str(ss.songs[s].get("bpm") or ""), "_id": s} for i, s in enumerate(ss.order)])
edited = st.data_editor(df, hide_index=True, disabled=["Title", "Key", "BPM"],
                        column_config={"_id": None, "Order": st.column_config.NumberColumn(min_value=1, step=1)},
                        key="order_editor", use_container_width=True)
c1, c2 = st.columns([2, 3])
set_name = c1.text_input("Set list name", "Set List")
order = list(edited.sort_values(["Order"], kind="stable")["_id"])
items = [[ss.songs[s], store.get(ss.songs[s]["title"])] for s in order]

if c2.button("Build set list files", type="primary"):
    with st.spinner("Building…"):
        set_html = render_html([(s, nt) for s, nt in items], notes_position, setlist_title=set_name, stage=stage)
        set_pdf = render_pdf([(s, nt) for s, nt in items], page, notes_position, fit, stage=stage, dark=dark)
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            used = set()
            for i, (s, nt) in enumerate(items, 1):
                fn = f"{i:02d}_{safe_name(s['title'])}"
                while fn in used:
                    fn += "_"
                used.add(fn)
                one = [[s, nt]]
                z.writestr(f"pdf/{fn}.pdf", _pdf(payload(one), page, notes_position, fit, stage, dark))
                z.writestr(f"html/{fn}.html", _html(payload(one), notes_position, stage))
                z.writestr(f"chordpro/{fn}.cho", to_chordpro(s, nt))
            z.writestr(f"{safe_name(set_name)}.pdf", set_pdf)
            z.writestr(f"{safe_name(set_name)}.html", set_html)
            z.writestr("band_notes.json", json.dumps(store.data, indent=2, ensure_ascii=False))
        ss.set_files = (set_name, set_pdf, set_html, zbuf.getvalue())

if ss.get("set_files"):
    nm, spdf, shtml, szip = ss.set_files
    c1, c2, c3 = st.columns(3)
    c1.download_button("📄 Set list PDF (all songs)", spdf, file_name=f"{safe_name(nm)}.pdf",
                       mime="application/pdf")
    c2.download_button("🌐 Set list HTML", shtml, file_name=f"{safe_name(nm)}.html", mime="text/html")
    c3.download_button("🗜️ Everything (.zip)", szip, file_name=f"{safe_name(nm)}.zip", mime="application/zip")
