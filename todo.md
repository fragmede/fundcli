# fundcli - Unknown Executable Auto-Discovery Feature

## In Progress
- [ ] Create `local_db.py` - SQLite wrapper for unknowns.db

## Pending
- [ ] Create `unknowns.py` - Investigation logic
  - [ ] `which_executable(exe)` - Find path
  - [ ] `get_file_type(path)` - script/binary detection
  - [ ] `run_help(exe)` - Capture --help output
  - [ ] `extract_copyright(path)` - Pattern matching
  - [ ] `suggest_classification(info)` - Heuristics
  - [ ] `investigate_executable(exe)` - Full pipeline
- [ ] Add CLI commands to `cli.py`
  - [ ] `fundcli unknowns` - List with investigation
  - [ ] `fundcli unknowns <exe>` - Detail view
  - [ ] `fundcli unknowns classify <exe> <class>`
  - [ ] `fundcli unknowns reset`
  - [ ] `fundcli unknowns --refresh`
- [ ] Integration with `fundcli analyze`
- [ ] Tests for unknowns feature

## Completed
- [x] Plan feature
- [x] Create todo.md

## Notes
- Database path: `~/.local/share/fundcli/unknowns.db`
- Auto-investigate on first run, cache thereafter
- `--refresh` flag to re-investigate all
