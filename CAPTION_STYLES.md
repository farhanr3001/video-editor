# Caption styling update

User-supplied Geometos Regular is now included in this private build. It is
listed as **Geometos**, with matching preview/export shapes. The supplied file
is not Geometos Soft Ultra. Its accompanying license PDF is retained in the
font assets. Font: 106,832 bytes; accompanying PDF: 229,448 bytes.

- Caption controls stay together at the top. Customize Caption expands directly beneath its checkbox; very small Inspectors can scroll instead of squeezing the header.
- Aa beside the emoji button changes the whole editor to uppercase, or lowercase if already uppercase. Existing multi-selection and undo rules apply.
- Remove periods at word endings affects generated captions only. Decimal points, URLs and punctuation inside words remain intact.
- Fade every word (3+ words per generated caption) fades each word in at its recorded speech onset, holds it, then fades the caption out.
- Word Highlight 2 (2+ words per generated caption) suggests sparse keywords using a deterministic English stop-word/length/number rule, with at least 1.5 seconds between suggestions. It does not infer emotional emphasis or duplicate proprietary CapCut logic. Timings displays the selected words on their highlight colour; right-click the Caption cell to highlight/unhighlight individual words, including a manually selected single-word caption.
- Punch is an original stronger pop/settle animation, not a verified copy of an iShowSpeed template.
- Glow follows text colour by default, with optional custom colour, radius and Inspector opacity controls. Preview glow tiles are cached. Bundled fonts and the new effects use shared glyph geometry in preview and export.
- The small font menu keeps Nirmala UI, familiar Windows faces and seven bundled OFL families. Existing project fonts remain selectable without expanding the menu back to every installed font. Hover in Auto Caption Style previews a font without changing the selection. Popups open below when there is enough screen space.

## Timing and compatibility

Karaoke, Emoji and Double Emoji single-word cards retain a static colour for their
entire visible duration, including speech hold padding. Important words receive
sparse emphasis; ordinary words stay on the base colour. Manual emphasis remains
available. Multiword cards retain recorded speech-timed karaoke. Auto emojis center
above the complete caption block (including wrapped lines), and distinct relevant
words may receive pops 0.8 seconds apart; identical emojis still have an 8-second
repeat limit. Output-coordinate glyph shaping keeps spacing/wrapping consistent
through preview zoom changes. Setup/card previews fit the complete text/emoji
composition inside their tiles; fitting does not change the saved caption style.

New local Whisper captions retain individual recognized word timings, independent of caption hold padding. Moves, duplicates, splits, merges, trims and ripple edits preserve/remap that metadata. Case-only edits retain it; replacing words clears stale timing/emphasis data. Existing projects and fallback speech engines without word timestamps use estimated timing; regenerate with Whisper for word synchronization. Recognition itself can still require manual correction.

## Font research and redistribution

This is a curated set, not a claim to enumerate every changing CapCut template. CapCut's own [font guide](https://www.capcut.com/resource/subtitle-font) and [Montserrat guide](https://www.capcut.com/resource/montserrat-font) discuss caption typography. [TikTok Sans](https://github.com/tiktok/TikTokSans) is explicitly intended for captions and is OFL licensed. The seven bundled families come from the [official Google Fonts repository](https://github.com/google/fonts), with their license notices retained: approximately 3.40 MB total.

[Geometos Soft](https://www.creativefabrica.com/product/geometos-soft/) is not bundled because its listing does not establish app-redistribution permission. If a licensed copy is installed in Windows, the family is included in the curated menu. No account purchases or subscriptions were made.
