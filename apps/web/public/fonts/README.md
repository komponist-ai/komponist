# Graph label font

`noto-sans-regular.ttf` is Noto Sans Regular (version 2.007, Copyright 2015-2021
Google LLC), distributed under the [SIL Open Font License 1.1][ofl].

It is checked in rather than fetched at runtime. Reagraph draws node and edge
labels inside the WebGL canvas with troika-three-text, which defaults to pulling
Roboto from `fonts.gstatic.com`. On a self-hosted Komponist that is a network
call the operator never asked for, and when it fails the graph renders with no
labels at all and no error. `apps/web/components/graph/KnowledgeGraphCanvas.tsx`
points `labelFontUrl` here instead, so labels work offline and look the same on
every deployment.

Only `.ttf`, `.otf` and `.woff` are usable here — troika cannot read `.woff2`.

[ofl]: https://openfontlicense.org/
