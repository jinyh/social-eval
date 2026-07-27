# School Leadership PPT Visual Assets Design

## Goal

Prepare the visual-asset design for a single school-leadership briefing slide about the China legal autonomous knowledge system AI-assisted evaluation results.

The slide should use the body-page template from `ref/交大模版.pptx`, not the earlier `ref/ref-ppt.png` header style. The visual assets must support a conservative, evidence-first message: the project has completed large-scale validation and produced a reviewable, traceable, promotable campus demonstration result.

## Source Context

- Content plan: `docs/reports/school-leadership-one-page-ppt-content-plan.md`
- PPT body template: `ref/交大模版.pptx`
- Existing body-template summary: `ref/交大模版.md`
- Knowledge network image: `ref/image/法学知识网络.png`
- Earlier visual reference: `ref/ref-ppt.png`

## Template Constraints

Use the body page of `ref/交大模版.pptx` as the visual frame.

Required template cues:

- 16:9 slide.
- White or very light gray geometric background.
- SJTU-style red line-art campus gate element near the top.
- SJTU / Artificial Intelligence Institute identity area from the template.
- Footer system with school motto, institute identity, and page number.
- Main content placed inside the template body region, not over the footer.

The page may use red-bordered evidence cards inside the body area, but it should not recreate the full top red-orange banner from `ref/ref-ppt.png`.

## Layout Design

Use a three-column evidence-card layout inside the body region.

### Title Area

Slide title:

`中国哲学社会科学自主知识创新（法学论文）AI辅助评价系统成果`

Central subtitle or ribbon:

`完成 1920 篇法学论文全量评价，形成“内容评价 + 归属判断 + 成果推广”闭环`

The subtitle may be rendered as a restrained SJTU-red rounded ribbon or inline subtitle, depending on available body-page spacing.

### Three Evidence Cards

Each card should have:

- White background.
- SJTU-red border.
- Subtle shadow.
- Small rounded title label.
- Image area.
- Short text area for editable PPT/SVG labels and numbers.

The three cards are equal-width by default. If space is tight, the middle knowledge-network card may be slightly wider, but the page should still read as a balanced three-part evidence chain.

## Asset Plan

### Left Card: Three Journal Covers

Purpose: show the authority and representativeness of the sample source.

Content:

- Cover of `中国社会科学`.
- Cover of `法学研究`.
- Cover of `中国法学`.

Source policy:

- Use recent formal covers from authoritative journal pages where possible.
- Prefer official or authoritative academic-source pages over low-resolution subscription-store images.
- Use covers from around 2025 if available, and avoid mixing very old covers unless no better source is available.

Visual treatment:

- Arrange the three covers as a clean equal-height triptych.
- Use consistent crop, size, and perspective.
- Do not over-tilt or make it look like advertising.
- Add editable labels below or above the covers in PPT/SVG, not inside generated raster art.

### Middle Card: Knowledge Network

Purpose: show the relationship and gaps between the education-ministry handbook system and eleven years of three-journal papers.

Use:

- `ref/image/法学知识网络.png`

Semantics:

- Blue nodes represent `《手册》`.
- Green nodes represent three-journal papers.
- Some green paper nodes are outside the handbook system.
- Some blue handbook nodes lack paper support.
- These gaps can motivate later expert review and knowledge-system refinement.

Treatment:

- Use the provided image directly.
- Do not ask `image_gen` to redraw it.
- Do not recolor or replace its blue-green semantics.
- Wrap it in the same SJTU-red evidence-card frame as the other columns.
- Add editable legend text outside the image: `蓝色：《手册》节点` and `绿色：三大刊论文节点`.

### Right Card: Campus Promotion Loop

Purpose: show the result-to-application path for school leadership: reviewed candidate results can support campus academic governance and social-science evaluation reform.

Use `image_gen` to create one raster visual for the image area only.

The generated visual must match the SJTU body-page template and the other two cards. It should look like a card illustration inside a formal university briefing slide, not like a standalone AI poster.

Concept:

`Top50 审阅成果 -> 专家复核 -> 学科建设 / 成果发现 / 评价改革`

The exact text and numbers will be overlaid later as editable PPT/SVG text, so the generated image should contain no readable text.

## image_gen Prompt Specification

Use case: `infographic-diagram`

Asset type: PowerPoint card illustration for the right column of a school-leadership briefing slide.

Primary request:

Create a clean institutional PowerPoint card illustration showing an expert review and campus promotion loop for AI-assisted academic evaluation results.

Style:

- Match a Shanghai Jiao Tong University body-page briefing template.
- White or very light warm gray background.
- SJTU-like deep red and orange-red accents.
- Subtle gold highlights only where useful.
- Restrained gray connector lines.
- Formal university reporting style.
- Clean business infographic, not a tech poster.

Composition:

- Centered closed-loop workflow.
- Abstract stack of academic documents or paper cards as the input node.
- Expert review node represented by a roundtable, checklist, or review stamp motif.
- Three downstream application nodes representing discipline development, landmark achievement discovery, and evaluation reform.
- Leave open whitespace at the top and bottom for later Chinese labels and bullet text.
- The image should fit naturally inside a white card with a red border.

Constraints:

- No Chinese text.
- No English text.
- No numbers.
- No logos.
- No watermark.
- No fake readable user interface.
- No human faces or identifiable people.
- No blue-green knowledge network visual, because the middle card already uses that visual language.
- No dark background.
- No cyberpunk, neon, sci-fi dashboard, or high-tech poster style.

Prompt core:

```text
Use case: infographic-diagram
Asset type: one PowerPoint card illustration, no text
Primary request: Create a clean institutional PowerPoint card illustration showing an expert review and campus promotion loop for AI-assisted academic evaluation results.
Style: match a Shanghai Jiao Tong University body-page briefing template; white or very light warm-gray background; SJTU-like deep red and orange-red accents; subtle gold highlights; restrained gray connector lines; formal university reporting style; clean business infographic, not a standalone tech poster.
Composition: centered closed-loop workflow with abstract academic document stack as input, expert review/checklist node, and three downstream application nodes for discipline development, landmark achievement discovery, and evaluation reform; leave open whitespace at top and bottom for later Chinese labels.
Constraints: no readable text, no Chinese, no English, no numbers, no logos, no watermark, no fake UI screenshots, no human faces, no blue-green knowledge network, no dark background, no cyberpunk, no neon, no sci-fi dashboard.
```

## Editable Text and Numeric Overlays

All exact labels, numbers, and Chinese explanatory text must be added later as editable PPT/SVG text.

Do not rely on raster images for:

- `1920`
- `Top102`
- `Top50`
- `14.873 -> 7.237`
- `175 项对应`
- Journal names
- Knowledge-network legend
- Right-card application labels

This avoids hallucinated or unreadable AI-generated text.

## Acceptance Criteria

- The page uses `ref/交大模版.pptx` body-page visual language.
- The three cards clearly map to: source authority, knowledge-structure evidence, and promotion loop.
- The left journal-cover card uses authoritative and consistent cover images.
- The middle card uses `ref/image/法学知识网络.png` without recoloring or redrawing.
- The right `image_gen` image visually matches the template and does not look like a separate poster.
- All precise numbers and Chinese labels remain editable outside generated raster images.
- The final slide can be understood by school leaders in about 30 seconds.

## Out of Scope

- Generating the final PPTX.
- Downloading final journal-cover files.
- Running `image_gen`.
- Editing or redrawing the knowledge-network image.
- Adding animations.
- Writing a full presentation deck.
