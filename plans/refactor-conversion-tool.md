# feat: Refactor conversion scripts into modern CLI application

## Overview

Refactor two standalone Python conversion scripts (`convert_copilot.py` and `convert_oc.py`) into a modern, installable CLI application that transfers Claude Code agents, skills, commands, and MCPs to OpenCode and Copilot formats.

## Problem Statement

**Current State:**
- Two standalone scripts with ~40% code duplication (500+ lines of shared logic)
- No testing infrastructure (0% test coverage)
- No packaging or distribution mechanism (cannot `pip install`)
- Inconsistent error handling and no logging system
- No documentation for users
- Hardcoded paths

**Pain Points:**
- Users must run scripts directly, cannot install as package
- Code duplication makes maintenance difficult
- No validation of input/output formats
- Poor user experience (no dry-run mode)

## Proposed Solution

Create `claude-migrate` - a modern Python CLI application with:

1. **Direct Conversions**: Simple module-based converters for each format (no plugin system)
2. **Shared Core**: Extract duplicate code into reusable utilities
3. **Type Safety**: Pydantic models for data structures
4. **Modern CLI**: Typer-based CLI with clean interface
5. **Testing**: pytest-based test suite with 60-70% coverage
6. **Packaging**: Proper Python package with `pyproject.toml` and PyPI distribution
7. **Documentation**: Comprehensive README with examples

**High-Level Architecture:**

```
┌─────────────────────────────────────┐
│         CLI Layer (Typer)          │
│      convert command only            │
└─────────────────────────────────────┘
                │
┌───────────────┴─────────────────────┐
│     Format Modules                    │
│  - claude_code.py  (load)          │
│  - opencode.py     (convert/save)   │
│  - copilot.py      (convert/save)   │
└─────────────────────────────────────────┘
```

## Technical Considerations

### Architecture

**Simple Two-Layer Architecture:**
- CLI Layer: Typer command interface
- Format Layer: Simple modules for each format

**Benefits:**
- Clear separation of concerns
- Easy to add new formats (just add a module)
- Testable at each layer
- No unnecessary abstraction

**Why No Plugin System:**
- Only need 3 formats (Claude Code, OpenCode, Copilot)
- Adding a 4th format is as simple as creating a new file
- Plugin registry adds complexity without proportional benefit

### Performance

**Approach:**
- Sequential processing of all items
- No caching (conversions are fast for typical use)
- All configs loaded into memory

**Impact:** Excellent performance for typical use (< 100 items, < 5 seconds)

### Security

**Risks Addressed:**
1. **Sensitive Data**: MCP configs may contain API keys in env vars
   - Solution: Default to redacting secrets, require `--include-secrets` flag

2. **Path Traversal**: User-provided paths could escape target directory
   - Solution: Validate all paths resolve within target directory

3. **Command Injection**: MCP command/args could be exploited
   - Solution: Validate input, escape shell commands if needed

4. **File Permissions**: No validation of read/write access
   - Solution: Pre-flight check of all source/target paths

## Acceptance Criteria

### Core Functionality

- [ ] CLI installed via `pip install claude-migrate` with `claude-migrate` command available
- [ ] Convert Claude Code agents/commands/skills/MCPs to OpenCode format (both dir and json formats)
- [ ] Convert Claude Code agents/commands/skills/MCPs to Copilot format
- [ ] Shared utilities module extracted from duplicate code (~300 lines reduced to ~100 lines)
- [ ] Pydantic models for all format schemas (Claude Code, OpenCode, Copilot)

### CLI Features

- [ ] `claude-migrate convert --to <format>` command
- [ ] `--output <path>` flag for custom output directory
- [ ] `--format <dir|json>` flag for OpenCode output format
- [ ] `--dry-run` flag to preview changes without writing
- [ ] `--force` flag to overwrite existing files
- [ ] `--verbose` flag for detailed logging
- [ ] Clear error messages with file paths and actionable guidance

### Testing

- [ ] pytest configuration with fixtures
- [ ] Unit tests for conversion functions (target: 60-70% coverage)
- [ ] Integration tests for CLI command
- [ ] Test fixtures for sample configs
- [ ] CI/CD pipeline (GitHub Actions) running tests on push

### Documentation

- [ ] README.md with quick start guide, installation, and examples
- [ ] In-code docstrings for API reference

### Code Quality

- [ ] All duplicate code extracted to shared module
- [ ] Type hints enforced with mypy
- [ ] Linting with ruff
- [ ] Pre-commit hooks configured
- [ ] No Chinese comments (standardized to English)

### Error Handling

- [ ] Consistent error handling with specific exception types
- [ ] All errors include file paths and actionable messages
- [ ] Graceful handling of missing files, invalid YAML, permission errors

## Success Metrics

- **Code Duplication**: Reduce from 40% to <5% duplicate code
- **Test Coverage**: Achieve 60-70% coverage for conversion logic
- **Package Distribution**: Successfully publish to PyPI and installable via pip
- **User Experience**: Conversion time for typical workspace (< 100 items) < 5 seconds
- **Documentation**: README is clear for first-time users

## Dependencies

**Python Version:** 3.11+

**Core Dependencies:**
- `typer>=0.12.0` - CLI framework
- `pydantic>=2.5.0` - Data validation and models
- `pyyaml>=6.0.0` - YAML parsing
- `rich>=13.7.0` - Rich terminal output

**Development Dependencies:**
- `pytest>=7.4.0` - Testing framework
- `pytest-cov>=4.1.0` - Coverage reporting
- `ruff>=0.1.0` - Linting and formatting
- `mypy>=1.8.0` - Type checking
- `pre-commit>=3.6.0` - Git hooks

## Implementation Phases

### Phase 1: Foundation & Utilities (Week 1)

**Tasks:**
1. Create package structure with `pyproject.toml`
2. Set up pytest, ruff, mypy configurations
3. Create CI/CD pipeline (GitHub Actions)
4. Extract shared utilities module from duplicate code:
   - `Statistics` class
   - `expand_vars()` function
   - `parse_frontmatter()` function
   - `ensure_dir()` function
   - `strip_jsonc_comments()` function
   - `load_jsonc()` function

**Deliverables:**
- Package structure: `src/claude_migrate/`
- `tests/` directory with pytest config
- `utils.py` module (~100 lines extracted)
- `pyproject.toml` with all dependencies

**Success Criteria:**
- `pip install -e .` works
- pytest runs with 0 tests (no failures)
- ruff passes on extracted code
- mypy type checking passes

### Phase 2: Format Implementation (Week 2)

**Tasks:**
1. Define Pydantic models for data structures:
   - Claude Code format (agents, commands, skills, MCP)
   - OpenCode format
   - Copilot format

2. Implement format modules:
   - `claude_code.py`: Load agents/commands/skills/MCPs from `~/.claude/`
   - `opencode.py`: Convert to OpenCode directory or JSONC format
   - `copilot.py`: Convert to Copilot format

3. Write unit tests for format modules

**Deliverables:**
- `models.py` with all Pydantic schemas
- `formats/claude_code.py` (200 lines)
- `formats/opencode.py` (250 lines)
- `formats/copilot.py` (200 lines)
- Unit tests for format logic

**Success Criteria:**
- Pydantic validation catches invalid configs
- Conversions work end-to-end
- 60-70% coverage for conversion logic

### Phase 3: CLI Implementation (Week 3)

**Tasks:**
1. Create Typer CLI structure:
   ```bash
   claude-migrate convert --to <format> [--output PATH] [--format dir|json] [--dry-run] [--force] [--verbose]
   ```

2. Implement `convert` command:
   - Load Claude Code format
   - Call appropriate target converter
   - Handle dry-run mode
   - Display statistics

3. Write integration tests for CLI

**Deliverables:**
- `cli.py` with convert command (~150 lines)
- Integration tests for CLI workflow

**Success Criteria:**
- All CLI flags work correctly
- Help text is clear
- Exit codes are correct (0=success, 1=error)

### Phase 4: Testing & Quality (Week 4)

**Tasks:**
1. Create test fixtures:
   - Minimal Claude Code config (1 agent, 1 command, 1 skill)
   - Typical config (10 items across all types)
   - Edge cases (malformed YAML, missing fields)

2. Write integration tests:
   - Full convert workflow for OpenCode
   - Full convert workflow for Copilot
   - Error scenarios

3. Add CI/CD pipeline:
   - Run tests on every push
   - Run linting and type checking
   - Measure coverage (enforce 60% minimum)

4. Add pre-commit hooks:
   - Ruff for linting
   - Mypy for type checking

**Deliverables:**
- `tests/fixtures/` with sample configs
- `tests/integration/` directory
- `.github/workflows/test.yml`
- `.pre-commit-config.yaml`

**Success Criteria:**
- 60-70% code coverage
- All tests pass in CI
- No linting or type errors

### Phase 5: Documentation & Release (Week 5-6)

**Tasks:**
1. Write comprehensive README.md:
   - Project description
   - Installation instructions
   - Quick start guide
   - Common use cases with examples
   - Troubleshooting FAQ

2. Finalize `pyproject.toml`:
   - Version management
   - Entry point configuration

3. Create release artifacts:
   - Source distribution (sdist)
   - Wheel distribution (bdist_wheel)
   - Test installation from artifacts

4. Test distribution:
   - Install from PyPI test repo
   - Verify all commands work
   - Test on Python 3.11 and 3.12

5. Publish to PyPI:
   - Tag release in git
   - Upload to PyPI
   - Create GitHub release with changelog

**Deliverables:**
- Published PyPI package
- GitHub release with changelog
- Comprehensive README

**Success Criteria:**
- `pip install claude-migrate` works
- Package works on Python 3.11 and 3.12
- Zero critical bugs reported in first 30 days

## Alternative Approaches Considered

### Approach 1: Full Plugin System (Rejected)

**Description:** Build extensible plugin architecture with entry points and registry

**Why Rejected:**
- Only need 3 formats (Claude Code, OpenCode, Copilot)
- Adding new formats is simple: just create a new module file
- Plugin registry adds complexity without proportional benefit
- YAGNI violation (building for hypothetical future needs)

### Approach 2: Intermediate Representation (Rejected)

**Description:** Convert Claude → Intermediate → Target (2 conversions)

**Why Rejected:**
- Adds unnecessary layer of abstraction
- Direct format-to-format conversion is simpler
- No clear benefit for 3 fixed formats
- More code to maintain

### Approach 3: No Testing (Rejected)

**Description:** Skip test suite to ship faster

**Why Rejected:**
- Refactoring existing code risks introducing bugs
- Tests prevent regressions and provide safety net
- Essential for production-quality tool

### Approach 4: Extensive Documentation (Rejected)

**Description:** Write multiple docs (user guide, API reference, plugin dev guide)

**Why Rejected:**
- Writing docs before knowing what users need is premature
- Start with excellent README, add more docs based on user feedback
- Auto-generated API reference from docstrings is sufficient

**Chosen Approach:** Simple, pragmatic refactor with focus on core value

## References & Research

### Internal References

**Existing Code:**
- `convert_copilot.py:22-43` - Statistics class (duplicate)
- `convert_copilot.py:47-62` - expand_vars function (duplicate)
- `convert_copilot.py:64-109` - parse_frontmatter function (duplicate)
- `convert_oc.py:26-52` - Statistics class (duplicate)
- `convert_oc.py:57-74` - expand_vars function (duplicate)
- `convert_oc.py:77-129` - parse_frontmatter function (duplicate)

### External References

**Best Practices:**
- [Typer Documentation](https://typer.tiangolo.com/) - CLI framework
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [Click Testing](https://click.palletsprojects.com/en/8.1.x/testing/) - CLI testing patterns
- [Python Packaging Guidelines](https://packaging.python.org/en/latest/) - Modern packaging

**Testing Strategies:**
- [Pytest Documentation](https://docs.pytest.org/) - Testing framework
- [Real Python CLI Testing](https://realpython.com/python-cli-testing/) - Testing patterns

## Open Questions

### Critical

1. **Merge Strategy for Conflicts**: When same item exists at user/project/plugin levels, what is precedence order?
   - **Assumption**: User > Project > Plugin (highest priority wins)
   - **Validation**: Document clearly in README

2. **Sensitive Data Handling**: How should MCP configs with API keys be handled?
   - **Assumption**: Default to redacting secrets, require explicit `--include-secrets` flag
   - **Validation**: Test with various MCP configs

## Appendices

### Appendix A: Duplicate Code Inventory

**Identical Functions:**
- `Statistics` class: `convert_copilot.py:22-43` = `convert_oc.py:26-52`
- `expand_vars()`: 99% match between both files
- `parse_frontmatter()`: 95% match between both files
- `ensure_dir()`: 100% match between both files
- `strip_jsonc_comments()`: 100% match between both files
- `load_jsonc()`: 100% match between both files

**Total Duplicated Lines: ~300 lines → Reduced to ~100 lines in shared module**

### Appendix B: Format Comparison Matrix

| Feature | Claude Code | OpenCode | Copilot |
|---------|-------------|----------|----------|
| **Agents** | `.md` with YAML frontmatter | `.md` in `agent/` or in `opencode.jsonc` | `.agent.md` in `.github/agents/` |
| **Commands** | `.md` with YAML frontmatter | `.md` in `command/` or in `opencode.jsonc` | `.prompt.md` in `.github/prompts/` |
| **Skills** | Directory with `SKILL.md` | Directory with `SKILL.md` | Directory with `SKILL.md` |
| **MCP** | `.mcp.json` | `mcp.json` or in `opencode.jsonc` | `mcp.json` |
| **Namespace** | N/A | `plugin:command` (colon) | `plugin-command` (hyphen) |
| **Format Options** | N/A | dir or json | Fixed structure |

### Appendix C: Project Structure

```bash
claude_migrate/
├── src/
│   └── claude_migrate/
│       ├── __init__.py
│       ├── cli.py              # Typer CLI (~150 lines)
│       ├── utils.py            # Shared utilities (~100 lines)
│       ├── models.py           # Pydantic models (~100 lines)
│       └── formats/
│           ├── __init__.py
│           ├── claude_code.py  # Load Claude Code (~200 lines)
│           ├── opencode.py     # Convert to OpenCode (~250 lines)
│           └── copilot.py      # Convert to Copilot (~200 lines)
├── tests/
│   ├── fixtures/               # Sample configs
│   │   ├── claude_minimal/
│   │   ├── claude_typical/
│   │   └── claude_edge_cases/
│   ├── test_utils.py
│   ├── test_formats.py
│   └── test_cli.py
├── pyproject.toml
├── README.md
└── .pre-commit-config.yaml
```

**Total Code: ~1000 lines** (vs. 3000+ lines in original plan, 67% reduction)

### Appendix D: Example CLI Usage

```bash
# Basic conversion
claude-migrate convert --to opencode

# Custom output directory
claude-migrate convert --to opencode --output ./my-configs

# Dry run to preview
claude-migrate convert --to opencode --dry-run

# Force overwrite existing files
claude-migrate convert --to opencode --force

# Verbose output for debugging
claude-migrate convert --to opencode --verbose

# OpenCode JSON format
claude-migrate convert --to opencode --format json

# Convert to Copilot
claude-migrate convert --to copilot
```

### Appendix E: Testing Strategy

**Unit Tests:**
- Test each helper function (expand_vars, parse_frontmatter, etc.)
- Test each conversion function with various inputs
- Test Pydantic model validation
- Target: 60-70% coverage

**Integration Tests:**
- Test full convert workflow for OpenCode (dir format)
- Test full convert workflow for OpenCode (JSON format)
- Test full convert workflow for Copilot
- Test error scenarios (invalid YAML, missing files)
- Test CLI flags and options

**Fixtures:**
- `fixtures/claude_minimal/` - 1 agent, 1 command, 1 skill
- `fixtures/claude_typical/` - 10 items across all types
- `fixtures/claude_edge_cases/` - malformed YAML, missing fields

**Coverage Goals:**
- Conversion logic: 70% coverage
- CLI commands: 60% coverage
- Overall: 60-70% coverage
