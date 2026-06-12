# nexaOSweb Flow Visual Spec
The written design bible for the web frontend. The canonical visual reference is the prototype file design/flow_prototype_v4.html committed into the repo. This spec puts its rules in words so Claude Code builds to them in React and Tailwind.

## Principle
A horizontal panorama of seven stage cards over a holographic red and orange backdrop. Orange is the only brand color. Green, gold, and red appear only as small status signals. All colors and fonts are CSS variables in a single tokens file. Components never hardcode hex.

## Tokens (define as CSS variables, mirror the prototype)
- canvas warm near black background, surface a lifted warm dark panel for cards.
- accent orange #FF7320, accent high #FF8A42, accent deep #FF4D1A.
- status green #52CC75, gate gold #F5BD42, danger red #DC321A.
- sidebar gradient from #9A1B0C to #330708.
- text cream #F4EEE4, muted warm grey, faint warmer grey.
- border a low opacity warm orange.
- font sans is the system stack, font mono is a monospace stack used for all small uppercase labels, meta, paths, percentages, and model names.

## Layout
- A fixed left sidebar about 206 px, the red gradient, brand at top, nav rows with an orange icon and a cream label, the active row a solid orange fill with a soft glow.
- A main area with the holographic backdrop, a page title in bold, a mono section label with a status dot, and the content.

## Stage card pattern
Each stage is a column laid left to right inside a horizontal scroll deck. A column has a mono STAGE 0N badge with a status dot, a bold title, a mono path or descriptor sublabel, then one or more cards. A card is translucent glass with a subtle moving sheen, a one pixel warm border, and a glow on the active stage. A card header is a mono label on the left and an optional right aligned mono meta on the same line.

## Connector wire
A glowing curved wire connects each card to the next, drawn in a canvas or svg layer behind the cards. Accent gradient stroke, soft glow, a slow flowing dash, the active segment brighter. It must never render in front of a card.

## Holographic backdrop
A slowly rotating wireframe sphere of orange and red points and edges with depth shading and a slight parallax on pointer position, drawn on a canvas with requestAnimationFrame, kept faint and behind everything. Honor prefers reduced motion with a static frame.

## The seven stages
- 01 Capture is an interactive box. A drop target, a project name field, a description field, source chips (note, voice, md, pdf, url, youtube, image, telegram, slack), a Generate with AI button, a details modal, and a Capture button. Sublabel a project path.
- 02 Classify shows a shape pill, a confidence percent in mono, a right aligned model key, and a decision log modal with route, model, rationale, and a reasoning summary, plus export. No hidden chain of thought.
- 03 Route lists eight workflows as rows with a status dot each. The winning route is lit. Non project routes show a terminal note and dim the later stages.
- 04 Process shows a project folder, a mono file tree with project_plan.md draft, the build destination in accent, and an open plan modal that renders the markdown.
- 05 Clarify shows the clarifying questions, selectable integration chips matched from settings, an open preview modal, and a continue action.
- 06 Human Gate shows the map, integrations, and build destination, with Approve, Send back, and Archive, plus links to plan and preview.
- 07 Execute shows promote, the build destination, a worker list that lights up, and a link into the Projects view.

## Buttons, pills, controls
- Primary button is a solid orange fill with white text.
- Outline button is an accent border with accent text, often with an arrow glyph.
- Muted button is a translucent grey fill with muted text.
- Pills are mono uppercase with an outline, accent for brand, green for product tags, grey for neutral, and a solid accent pill for the classify shape.
- Toggle is accent when on. Stepper shows a value with up and down chevrons in mono. Slider is an accent track with a knob and a mono percent.

## Do and do not
- Do reuse a shared set of primitives (Sidebar, MonoLabel, StatusDot, StageTrack, GlassCard, Pill, Button) across the app.
- Do keep text on surface and glass for chrome.
- Do not introduce blue or the reference palette. The reference is structure only.
- Do not hardcode colors or fonts in components.
- Do not place the connector wire in front of the cards.
