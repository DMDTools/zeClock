# Implementation Plan: GIF Directory Rotation

## Overview

Extend the `GifPlugin` to support multiple GIF source directories, each with a probability weight and recursive-traversal flag. The implementation modifies `gif_plugin.py` (new dataclass, new parsing/selection methods, updated config_schema), updates existing tests, and adds property-based tests using Hypothesis.

## Tasks

- [x] 1. Add DirectoryEntry dataclass and parsing logic
  - [x] 1.1 Define `DirectoryEntry` dataclass and implement `_resolve_directories` method
    - Add `from dataclasses import dataclass` import at module level in `gif_plugin.py`
    - Define `DirectoryEntry` dataclass with fields: `path: Path`, `weight: int = 50`, `recursive: bool = True`
    - Implement `_resolve_directories(self, raw_dirs: list) -> List[DirectoryEntry]` as a private method on `GifPlugin`
    - Method parses list of dicts, skips entries with missing/empty path or non-existent directories (logging warnings), defaults weight to 50 if invalid, defaults recursive to True
    - _Requirements: 1.1, 1.2, 1.5, 2.3_

  - [ ]* 1.2 Write property test for config parsing defaults (Property 1)
    - **Property 1: Config parsing produces correct DirectoryEntry objects with defaults**
    - Use Hypothesis to generate lists of raw dicts with optional weight/recursive keys
    - Assert parsed `DirectoryEntry` objects have correct path, weight defaults to 50, recursive defaults to True
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 1.3 Write property test for invalid entry filtering (Property 2)
    - **Property 2: Invalid entries are filtered from parsed results**
    - Use Hypothesis to generate mixed lists of valid and invalid entry dicts
    - Assert only valid entries (non-empty path pointing to existing directory) appear in parsed results
    - **Validates: Requirements 1.5, 2.3**

- [x] 2. Implement weighted GIF selection logic
  - [x] 2.1 Implement `_select_gif` method with weighted random directory choice
    - Add `_select_gif(self, entries: List[DirectoryEntry]) -> Path` method to `GifPlugin`
    - For each entry: use `rglob("*.gif") + rglob("*.GIF")` if recursive, else `glob("*.gif") + glob("*.GIF")`
    - Filter to directories containing at least one GIF file
    - Use `random.choices` with weights for directory selection, then `random.choice` for file selection
    - Raise `PluginNotConfiguredError` if no GIF files found in any directory
    - _Requirements: 3.1, 3.2, 3.3, 2.1, 2.2_

  - [ ]* 2.2 Write property test for selection from non-empty directories (Property 3)
    - **Property 3: GIF selection only comes from non-empty directories**
    - Use Hypothesis with temp directories containing varying GIF file counts
    - Assert selected GIF always belongs to a directory that has at least one GIF
    - **Validates: Requirements 3.1, 3.2**

  - [ ]* 2.3 Write property test for all-empty raises error (Property 4)
    - **Property 4: All-empty configuration raises PluginNotConfiguredError**
    - Use Hypothesis to generate DirectoryEntry lists where all paths are empty of GIF files
    - Assert `PluginNotConfiguredError` is raised
    - **Validates: Requirements 3.3**

- [x] 3. Update `initialize()` and `config_schema` in GifPlugin
  - [x] 3.1 Rewrite `initialize()` to use `gif_dirs` with fallback to default
    - Modify `initialize(self, config: dict)` to read `config.get("gif_dirs")` instead of `config.get("gif_dir")`
    - If `gif_dirs` is absent or empty, fall back to `[{"path": str(DEFAULT_GIF_DIR), "weight": 50, "recursive": True}]`
    - Call `_resolve_directories()` then `_select_gif()` to get a random GIF path
    - Keep the existing background loading thread logic (`_load_gif_background`) unchanged
    - Remove old single-directory logic (resolve gif_dir, rglob, random.choice)
    - _Requirements: 1.1, 1.4, 3.1_

  - [x] 3.2 Update `config_schema` property to declare `gif_dirs` list field
    - Replace the single `gif_dir` text field with a `gif_dirs` field of type `list`, required=True
    - Set label to `"GIF Directories"`
    - Set description to `"List of directory entries. Each entry: path (string), weight (integer, default 50), recursive (boolean, default true)"`
    - _Requirements: 4.1, 4.2_

- [x] 4. Checkpoint - Verify core implementation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update and add unit tests
  - [x] 5.1 Update existing `test_gif_config.py` tests for new config schema
    - Update `TestConfigSchema` to check for `gif_dirs` field with `field_type="list"`, `required=True`, and label `"GIF Directories"`
    - Update `TestPluginNotConfiguredError` tests to pass `gif_dirs` list format instead of `gif_dir` string
    - Test fallback behavior when `gif_dirs` is absent (falls back to DEFAULT_GIF_DIR)
    - _Requirements: 1.4, 4.1, 4.2_

  - [ ]* 5.2 Write unit tests for recursive vs non-recursive traversal
    - Create temp directory with nested subdirectories containing GIF files
    - Test that `recursive=True` finds GIFs in subdirectories
    - Test that `recursive=False` only finds GIFs in the immediate directory
    - _Requirements: 2.1, 2.2_

  - [ ]* 5.3 Write unit tests for weighted selection and REST API config roundtrip
    - Test weighted selection with mocked random to verify directory proportionality logic
    - Test that existing `POST /api/config/plugins` with `gif_dirs` persists and triggers reconfigure
    - Test that `GET /api/config/plugins` returns `gif_dirs` entries with all fields
    - _Requirements: 3.1, 5.1, 5.2_

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The REST API does not require code changes — existing endpoints already handle the new config structure
- The `PluginConfig` and `PluginManager` classes are unchanged; all changes are internal to `GifPlugin`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1", "3.2"] },
    { "id": 3, "tasks": ["5.1", "5.2", "5.3"] }
  ]
}
```
