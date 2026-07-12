# School Leadership PPT Visual Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the visual asset set for one school-leadership PPT body slide using `ref/交大模版.pptx`: three journal covers, the existing knowledge-network image, and one matching `image_gen` right-card illustration.

**Architecture:** Keep assets project-local and auditable under a dedicated slide-asset directory. Use authoritative web sources for journal covers, preserve the provided knowledge-network image unchanged, and generate only the right-card illustration with `image_gen`; all exact labels and numbers remain editable in the final PPT/SVG layer.

**Tech Stack:** Shell inspection with `rg`/`find`, browser/web lookup for journal-cover sources, built-in `image_gen` for one raster illustration, optional Pillow/ImageMagick-style local inspection for dimensions, Markdown manifests for provenance.

---

## File Structure

- Create: `ref/image/school-leadership-ppt-assets/`
  - Holds final source images for this slide.
- Create: `ref/image/school-leadership-ppt-assets/README.md`
  - Asset manifest, provenance, usage notes, and prompt record.
- Create: `ref/image/school-leadership-ppt-assets/journals/`
  - Holds three journal-cover image files.
- Copy: `ref/image/法学知识网络.png`
  - Copy into the asset directory only if needed by the final PPT build; do not alter the original.
- Create: `ref/image/school-leadership-ppt-assets/right-card-campus-promotion-loop.png`
  - The selected `image_gen` output for the right card.
- Do not modify: `ref/交大模版.pptx`
- Do not modify: `ref/image/法学知识网络.png`
- Do not generate: final PPTX in this plan unless the user explicitly asks in the next execution step.

## Task 1: Create Asset Workspace and Manifest

**Files:**
- Create: `ref/image/school-leadership-ppt-assets/README.md`
- Create directory: `ref/image/school-leadership-ppt-assets/journals/`

- [x] **Step 1: Create directories**

Run:

```bash
mkdir -p ref/image/school-leadership-ppt-assets/journals
```

Expected: directories exist.

- [x] **Step 2: Create initial manifest**

Write `ref/image/school-leadership-ppt-assets/README.md` with:

```markdown
# School Leadership PPT Visual Assets

Purpose: visual assets for one school-leadership body slide using `ref/交大模版.pptx`.

## Assets

| Asset | Path | Source | Usage | Notes |
|---|---|---|---|---|
| 中国社会科学 cover | `journals/` | To be filled during Task 2 | Left card | Use authoritative recent cover |
| 法学研究 cover | `journals/` | To be filled during Task 2 | Left card | Use authoritative recent cover |
| 中国法学 cover | `journals/` | To be filled during Task 2 | Left card | Use authoritative recent cover |
| Knowledge network | `../法学知识网络.png` | User provided | Middle card | Preserve blue/green semantics |
| Campus promotion loop | `right-card-campus-promotion-loop.png` | image_gen | Right card | No text/numbers/logos |

## Prompt

To be filled during Task 3 after image generation.
```

- [x] **Step 3: Verify manifest exists**

Run:

```bash
test -f ref/image/school-leadership-ppt-assets/README.md
```

Expected: exit code 0.

## Task 2: Collect Three Journal Covers

**Files:**
- Create: `ref/image/school-leadership-ppt-assets/journals/chinese-social-sciences-cover.*`
- Create: `ref/image/school-leadership-ppt-assets/journals/law-science-cover.*`
- Create: `ref/image/school-leadership-ppt-assets/journals/china-legal-science-cover.*`
- Modify: `ref/image/school-leadership-ppt-assets/README.md`

- [x] **Step 1: Search authoritative sources**

Use web search/browser lookup for recent formal covers of:

- `中国社会科学`
- `法学研究`
- `中国法学`

Priority:

1. Official journal website.
2. National Philosophy and Social Sciences Documentation Center or equivalent authoritative academic database page.
3. University/library catalog with cover image.

Avoid low-resolution shopping/subscription images unless no better source exists.

- [x] **Step 2: Save each selected cover**

Save covers under `ref/image/school-leadership-ppt-assets/journals/` with stable names:

```text
chinese-social-sciences-cover.<ext>
law-science-cover.<ext>
china-legal-science-cover.<ext>
```

Do not overwrite if files already exist; use `-v2` suffix if needed.

- [x] **Step 3: Record provenance**

Update the manifest table with:

- Exact source URL.
- Journal issue/year if known.
- Any caveat about source quality.

- [x] **Step 4: Inspect dimensions**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
from PIL import Image
for p in sorted(Path('ref/image/school-leadership-ppt-assets/journals').glob('*')):
    if p.is_file():
        im = Image.open(p)
        print(p.name, im.size, im.mode)
PY
```

Expected: all three covers open successfully and have plausible portrait dimensions.

## Task 3: Generate Right-Card Campus Promotion Loop Illustration

**Files:**
- Create: `ref/image/school-leadership-ppt-assets/right-card-campus-promotion-loop.png`
- Modify: `ref/image/school-leadership-ppt-assets/README.md`

- [x] **Step 1: Use imagegen skill**

Use @imagegen with the built-in `image_gen` tool, not the CLI fallback.

Prompt:

```text
Use case: infographic-diagram
Asset type: one PowerPoint card illustration, no text
Primary request: Create a clean institutional PowerPoint card illustration showing an expert review and campus promotion loop for AI-assisted academic evaluation results.
Style: match a Shanghai Jiao Tong University body-page briefing template; white or very light warm-gray background; SJTU-like deep red and orange-red accents; subtle gold highlights; restrained gray connector lines; formal university reporting style; clean business infographic, not a standalone tech poster.
Composition: centered closed-loop workflow with abstract academic document stack as input, expert review/checklist node, and three downstream application nodes for discipline development, landmark achievement discovery, and evaluation reform; leave open whitespace at top and bottom for later Chinese labels.
Constraints: no readable text, no Chinese, no English, no numbers, no logos, no watermark, no fake UI screenshots, no human faces, no blue-green knowledge network, no dark background, no cyberpunk, no neon, no sci-fi dashboard.
```

- [x] **Step 2: Save selected image into workspace**

Copy or move the selected built-in output into:

```text
ref/image/school-leadership-ppt-assets/right-card-campus-promotion-loop.png
```

Never leave the project-bound asset only under `$CODEX_HOME/generated_images`.

- [x] **Step 3: Inspect generated output**

Check visually that:

- It has no readable text or numbers.
- It uses white/light background with red-orange accents.
- It has enough whitespace for later labels.
- It looks like a card illustration for `ref/交大模版.pptx`, not a tech poster.

- [x] **Step 4: Update manifest prompt section**

Paste the final prompt and image filename into `README.md`.

## Task 4: Prepare PPT Placement Notes

**Files:**
- Modify: `ref/image/school-leadership-ppt-assets/README.md`

- [x] **Step 1: Add placement instructions**

Add a `## PPT Placement Notes` section:

```markdown
## PPT Placement Notes

- Use `ref/交大模版.pptx` body page as the base.
- Use three equal evidence cards inside the body area.
- Left card: three journal covers, equal height, consistent crop.
- Middle card: use `ref/image/法学知识网络.png` directly; do not recolor.
- Right card: use `right-card-campus-promotion-loop.png`; overlay Chinese labels and numbers as editable text.
- Keep all exact values editable: `1920`, `Top102`, `Top50`, `14.873 -> 7.237`, `175 项对应`.
```

- [x] **Step 2: Verify no forbidden raster text reliance**

Run:

```bash
rg -n "1920|Top102|Top50|14\\.873|7\\.237|175" ref/image/school-leadership-ppt-assets/README.md
```

Expected: values appear only in placement notes or manifest instructions, not as instructions to bake them into generated images.

## Task 5: Verification

**Files:**
- Read: `ref/image/school-leadership-ppt-assets/README.md`
- Read/inspect images under `ref/image/school-leadership-ppt-assets/`

- [x] **Step 1: Verify expected files**

Run:

```bash
find ref/image/school-leadership-ppt-assets -maxdepth 2 -type f | sort
```

Expected:

- `README.md`
- three journal cover image files
- `right-card-campus-promotion-loop.png`

- [x] **Step 2: Verify image readability**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
from PIL import Image
root = Path('ref/image/school-leadership-ppt-assets')
for p in sorted(root.rglob('*')):
    if p.is_file() and p.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}:
        im = Image.open(p)
        print(p.relative_to(root), im.size, im.mode)
PY
```

Expected: every saved image opens successfully.

- [x] **Step 3: Visual QA**

Open or inspect:

- journal covers
- `ref/image/法学知识网络.png`
- `right-card-campus-promotion-loop.png`

Expected:

- journal covers are recognizable and consistent enough for a small left-card triptych;
- knowledge network is unchanged;
- generated right-card illustration matches the body-template style and contains no unwanted text.

- [x] **Step 4: Report final paths**

Report:

- saved cover paths and source URLs;
- saved right-card path;
- whether any source quality caveat remains.
