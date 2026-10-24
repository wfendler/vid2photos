# Extraction scope

This repository contains the installed Python service's source, generalized configuration, a generic launchd template, a documented Shortcut rebuild, and offline tests. It is a new standalone source tree, without inherited Git history. The installed service and Photos library were not modified.

Public-copy differences: configurable tool directory, token path, and listen address; loopback default; token loading at startup rather than import; rejection of empty tokens; removal of URL/title/error-detail logging. The public copy additionally suppresses HTTP access/parser-error logs, rejects non-finite clip times, remuxes compatible video from other containers, and verifies the final MP4 container. This is not a full security review or a production migration.

Excluded: actual token, installed Shortcut database/export, logs, downloaded media, personal hostnames/addresses/paths, unrelated project files, and prior task artifacts. No original installer or shortcut-builder source was located. Setup is documented rather than represented as an exact reconstruction of a missing installer.

Published under the MIT License. Offline tests do not establish upstream website compatibility or Apple Photos import compatibility. A configured Shortcut remains a local secret-bearing artifact.

Publish only reviewed tracked files or a Git-tree archive. Do not upload a working-directory archive: ignored bytecode caches can contain absolute local paths.
