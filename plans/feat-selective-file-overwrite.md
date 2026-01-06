# feat: Selective file overwrite based on entity name matching

## Overview

Implement selective file overwrite in claude-migrate so that only files matching converted entities (by name) are overwritten, rather than requiring the entire target directory to be empty or using `--force` for blanket overwrites.

## Problem Statement

Currently, claude-migrate requires the `--force` flag to write to an existing output directory. When `--force` is used, it overwrites ALL files, which is destructive and inflexible. Users want incremental sync behavior where:

- Only files corresponding to converted entities are touched
- Existing custom files in the target directory are preserved
- The tool can be re-run safely to sync changes without losing unrelated configurations

## Proposed Solution

Remove the blanket `--force` requirement for existing directories. Instead:

1. **Check if output directory exists** - if not, proceed normally
2. **For each entity being converted**, check if the target file already exists
3. **If file exists**:
   - Compare entity name (e.g., agent name "my-agent" matches file `agent/my-agent.md`)
   - If names match, overwrite with automatic backup (current behavior with `--force`)
   - If names don't match (e.g., file from different source), skip and warn
4. **If file doesn't exist**, create it normally

### Entity-to-File Mapping

| Entity Type | Source | Target File Pattern |
|-------------|--------|---------------------|
| Agent | `agent.name` | `agent/<safe_name>.md` |
| Command | `command.name` | `command/<safe_name>.md` |
| Skill | `skill.name` | `skill/<skill.name>/SKILL.md` |
| MCP | server name key | `mcp.json` (single file, always overwrite if exists) |
| Plugin Agent | `pluginName:agent.name` | `agent/<pluginName>_<agent_name>.md` |
| Plugin Command | `pluginName:cmd.name` | `command/<pluginName>_<cmd_name>.md` |
| Plugin Skill | `pluginName:skill.name` | `skill/<pluginName>_<skill_name>/SKILL.md` |

### Safe Name Transformation

```python
# From opencode.py:61, copilot.py:31, utils.py:320-322
def sanitize_for_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()
```

## Technical Considerations

### CLI Changes (`cli.py:103-108`)

Current code:
```python
if output.exists() and not force:
    console.print(f"[red]Error: Output directory '{output}' already exists.[/red]")
    raise typer.Exit(code=1)
```

Proposed change:
- Remove the directory existence check that requires `--force`
- Keep `--force` for explicit blanket overwrite (backwards compatibility)
- Add new `--merge` flag for selective overwrite behavior (default when dir exists)

### Converter Changes

In `opencode.py` and `copilot.py`:
- Each `_save_*` method already calls `backup_file()` before writing
- Add pre-check: if file exists AND entity name matches, proceed with backup+write
- If file exists BUT entity name doesn't match, log warning and skip

### Statistics Tracking

Add new stat categories or extend existing:
- "Files" category: {"existing_matched", "existing_skipped", "created"}
- Track selective overwrite outcomes

## Acceptance Criteria

### Functional Requirements

- [ ] Running conversion to existing directory without `--force` no longer errors
- [ ] Files matching converted entities are overwritten with backup
- [ ] Files NOT matching any converted entity are preserved
- [ ] Warning is logged when skipping non-matching existing files
- [ ] `--force` flag still enables blanket overwrite for backwards compatibility
- [ ] `--merge` flag explicitly enables selective overwrite (becomes default)
- [ ] Dry run shows which files would be overwritten vs preserved
- [ ] MCP config (`mcp.json`) is handled appropriately (always sync if MCP servers exist)

### Edge Cases

- [ ] Agent/command names with special characters are sanitized consistently
- [ ] Plugin-namespaced entities (e.g., `plugin:my-agent`) map correctly
- [ ] Deleted entities in source leave stale files in target (won't be auto-deleted - by design)
- [ ] Name collisions: two source entities mapping to same file (error, not silent overwrite)
- [ ] Read-only target files (error with helpful message)
- [ ] Target directory is a file (error)

### Non-Functional Requirements

- [ ] Performance: O(n) where n = number of entities, not files in target
- [ ] Safety: Automatic backups before any overwrite
- [ ] UX: Clear console output showing what was overwritten vs skipped

## Success Metrics

1. **User friction reduction**: Zero errors when running in existing directory
2. **Preservation rate**: 100% of non-matching files preserved
3. **Backup verification**: All overwritten files have backups
4. **Naming consistency**: 100% match rate between entity names and file paths

## Dependencies & Risks

### Dependencies

- None - all changes are internal to claude-migrate

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Name collision between entities | Medium | Detect and error early with clear message |
| Inconsistent sanitization | High | Centralize name transformation in `utils.py` |
| User expects auto-deletion of stale files | Low | Document that selective mode doesn't delete stale files |
| `--force` behavior change | Low | Keep `--force` for blanket overwrite, add `--merge` for selective |

## References & Research

### Internal References

- `cli.py:103-108` - Current directory existence check
- `cli.py:110-111` - Comment about never deleting entire directory
- `opencode.py:61-62` - Agent file naming (`safe_name`)
- `opencode.py:97-98` - Command file naming
- `opencode.py:129-131` - Skill directory naming
- `utils.py:320-322` - `sanitize_filename()` function
- `utils.py:346-378` - `backup_file()` implementation

### External References

- rsync `--update` flag behavior (only copy files newer/different)
- Configuration management tools (Ansible, Chef) idempotent behavior

## Implementation Plan

### Phase 1: Core Logic

1. Modify `cli.py` to remove blanket directory existence check
2. Add `--merge` flag (defaults to True when dir exists)
3. Pass merge mode to converters
4. Update statistics tracking

### Phase 2: Converter Integration

1. Update `OpenCodeConverter` to check file existence before write
2. Update `CopilotConverter` similarly
3. Implement name matching logic
4. Add warning for skipped files

### Phase 3: Polish

1. Update dry-run to show overwrite vs skip decisions
2. Add verbose output for skipped files
3. Update documentation
4. Add tests for edge cases

## Future Considerations

- Add `--prune` flag to remove stale files not in source
- Add `--diff` flag to show what would change without writing
- Support for Three-way merge (source, target, base)
