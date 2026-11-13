# CodeMirror 6 bundle

`frontend/vendor/codemirror-6.js` is CodeMirror 6 (MIT, Copyright (C) 2018-2021 by Marijn Haverbeke and others) with the
Lezer parser helpers it needs (MIT), bundled into one script that sets the global
`CM`. `entry.js` lists what it exports; the application's editor is `frontend/src/app/51-config-editor.js`.

To rebuild it (only when a version in `build.sh` changes): install [Bun](https://bun.sh), then

    bash frontend/tools/codemirror/build.sh

The sources are cloned from GitHub at the tags written in `build.sh`; nothing is kept besides the bundle.
