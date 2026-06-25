# E11: Trade Notes

Attach large markdown notes to positions, stored on filesystem.

## Stories

- [ ] **E11-S01** `MVP` — Implement NoteManager: create note file under data/notes/{account_id}/{position_id}/, write metadata to trade_notes table
- [ ] **E11-S02** `MVP` — Implement note creation from file: `phantom note add <pos-id> --title "Thesis" --file ./my_thesis.md` — copy file content to note storage
- [ ] **E11-S03** `MVP` — Implement note creation via $EDITOR: `phantom note add <pos-id> --title "Review"` — open $EDITOR with temp file, save on close
- [ ] **E11-S04** `MVP` — CLI: `phantom note list <position-id>` — list notes with titles, sizes, timestamps
- [ ] **E11-S05** `MVP` — CLI: `phantom note show <note-id>` — print note content to stdout (pipe-friendly)
- [ ] **E11-S06** `MVP` — Implement note size tracking: update content_size on write, warn if approaching 5 MB
- [ ] **E11-S07** `P2` — Implement note edit: `phantom note edit <note-id>` — open existing note in $EDITOR
- [ ] **E11-S08** `P2` — Implement note search: grep across all notes in an account for a keyword
