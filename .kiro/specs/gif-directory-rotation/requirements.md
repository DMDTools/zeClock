# Requirements Document

## Introduction

This feature extends the GIF display plugin (`gif`) to support multiple source directories, each with an assigned probability weight and a recursive traversal flag. The configuration lives in `plugins.yaml` and is exposed through the existing REST API and Web UI via a config schema declaration.

## Glossary

- **GIF_Plugin**: The zeClock plugin identified by the name `gif` that displays animated GIFs on the DMD.
- **Directory_Entry**: A configuration item with a filesystem `path` (string), a `weight` (positive integer), and a `recursive` (boolean) flag.
- **Plugin_Config**: The YAML-based configuration system (`plugins.yaml`) that stores per-plugin settings.
- **Config_Schema**: The list of `ConfigField` objects declared by a plugin, used by the Web UI to auto-generate configuration forms.
- **REST_API**: The HTTP interface served by `RestRemote` that exposes plugin configuration endpoints.

## Requirements

### Requirement 1: Multiple Directory Configuration

**User Story:** As a zeClock owner, I want to configure multiple GIF source directories with path, weight, and recursive flag in `plugins.yaml`, so that I can organize my GIF collections into thematic folders.

#### Acceptance Criteria

1. THE GIF_Plugin SHALL accept a `gif_dirs` setting in Plugin_Config consisting of a list of Directory_Entry objects.
2. EACH Directory_Entry SHALL have a `path` (string, required), a `weight` (integer, default 50), and a `recursive` (boolean, default true) field.
3. THE Plugin_Config SHALL support the following YAML structure for the GIF_Plugin settings:
   ```yaml
   plugins:
     - name: gif
       frequency: 100
       settings:
         gif_dirs:
           - path: "/path/to/directory1"
             weight: 80
             recursive: true
           - path: "/path/to/directory2"
             weight: 20
             recursive: false
   ```
4. WHEN `gif_dirs` is absent from the GIF_Plugin settings, THE GIF_Plugin SHALL fall back to the platform-specific plugins subdirectory named "gif" as a single Directory_Entry with weight 50 and recursive true.
5. IF a Directory_Entry is missing the `path` field or the `path` is an empty string, THEN THE GIF_Plugin SHALL skip that entry and log a warning.

### Requirement 2: Recursive Subdirectory Traversal

**User Story:** As a zeClock owner, I want to choose whether a configured directory includes its subdirectories, so that I can control the scope of GIF discovery per directory.

#### Acceptance Criteria

1. WHILE `recursive` is true for a Directory_Entry, THE GIF_Plugin SHALL discover GIF files by traversing the directory and all nested subdirectories, matching files with the `.gif` extension case-insensitively.
2. WHILE `recursive` is false for a Directory_Entry, THE GIF_Plugin SHALL discover GIF files only in the immediate directory without descending into subdirectories, matching files with the `.gif` extension case-insensitively.
3. IF a Directory_Entry path does not exist or is not accessible, THEN THE GIF_Plugin SHALL skip that entry and log a warning.

### Requirement 3: Weighted Random Selection

**User Story:** As a zeClock owner, I want to assign a probability weight to each directory, so that some GIF collections appear more frequently than others.

#### Acceptance Criteria

1. WHEN a GIF is to be selected, THE GIF_Plugin SHALL first choose a directory with probability proportional to its weight relative to the sum of all weights, then pick a random GIF file from that directory.
2. WHEN a directory contains zero GIF files, THE GIF_Plugin SHALL exclude that directory from the selection pool.
3. IF all configured directories contain zero GIF files or have invalid paths, THEN THE GIF_Plugin SHALL raise a PluginNotConfiguredError indicating that no GIF files are available.

### Requirement 4: Config Schema for Web UI

**User Story:** As a zeClock owner, I want the Web UI to display a form for managing GIF directories, so that I can add, remove, and edit directories through the browser.

#### Acceptance Criteria

1. THE GIF_Plugin SHALL declare a `gif_dirs` field in its config_schema with field_type `list` and required set to True.
2. THE `gif_dirs` ConfigField SHALL include a description naming each Directory_Entry property: path (string), weight (integer, default 50), and recursive (boolean, default true).

### Requirement 5: REST API Configuration Support

**User Story:** As a zeClock owner, I want to save my GIF directory configuration through the REST API, so that the Web UI can persist changes.

#### Acceptance Criteria

1. WHEN a POST request to `/api/config/plugins` includes `gif_dirs` in the GIF_Plugin settings, THE REST_API SHALL persist the configuration to `plugins.yaml` and call `reconfigure_plugin` for the GIF_Plugin so changes take effect without a restart.
2. WHEN a GET request to `/api/config/plugins` is received, THE REST_API SHALL return the full plugin configuration as JSON including the `gif_dirs` list with each entry's `path`, `weight`, and `recursive` fields.
