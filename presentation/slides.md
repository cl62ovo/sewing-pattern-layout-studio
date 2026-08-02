---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    font-size: 26px;
  }
  section.lead h1 {
    font-size: 60px;
  }
  h2 {
    color: #b5482a;
  }
---

<!-- _class: lead -->

# Plush Pattern Studio

### From an idea to a sewable pattern — powered by AI

Team: **[Name A]** & **[Name B]**

---

## The Problem

Imagine you want to make a plush doll from scratch.

First, you need a technical 2D blueprint, complete with darts and seam allowances. You have to cut out each paper pattern piece, lay them strategically on a sheet of fabric to maximize material, trace every outline onto the cloth, and then carefully cut out all the fabric pieces. Only then can you start sewing them together into a 3D toy.

As you can see, this preparation requires both **geometric thinking** and **tedious manual work** — and it hits two very different groups hard.

---

## Who feels the pain

**For Professionals — the cost of complexity**
- Inefficient layouts: manual nesting is a slow, error-prone "geometric puzzle"
- High fabric waste: poor nesting wastes **15%–30%** of expensive material
- Alignment failure: matching stripes/checks by hand is unforgiving — one mistake ruins the garment

**For Beginners — the barrier to entry**
- The "Skill Wall": no pattern-making knowledge (darts, seam allowances, notches) keeps ideas stuck on paper
- Complexity paralysis: math, tool choices, and dense tutorials overwhelm novices before they start
- Low success rate: frustration kills the joy of handmade creation

<!-- [配图占位：手工排版/裁剪照片，或“专业 vs 新手”痛点对比图] -->

---

## Our Solution

That's why we created **Plush Pattern Studio** — to take care of this complex preparation so anyone can jump straight to the joy of creating.

- Describe your plush doll in plain language + pick a target height
- AI turns your words into a structured design spec
- A 3D model candidate is generated for you to confirm or regenerate
- The system auto-normalizes the mesh, plans seams, and unfolds panels
- Output: orthographic views + a 1:1 A4 sewing pattern, ready to print and cut

<!-- [配图占位：产品核心流程示意图] -->

---

## Live Demo — From Words to Pattern

1. Type a description + choose a height
2. AI drafts the design → a 3D model is generated
3. Preview and accept it (or regenerate with edits)
4. Get 2D pattern pieces + a printable A4 PDF

<!-- [占位符：demo 截图 / GIF] -->
<!-- [占位符：demo 截图 / GIF] -->

---

## Live Demo — For Professionals: Nest & Cut

<!-- demo placeholder — to be filled in -->

---

## How We Built It

**v1 — Vibe coding, fast iteration**
- Talked through requirements in a Q&A dialogue → wrote them into a design doc
- Vibe-coded a React MVP with Codex, then iterated

**v2 — Adding the real backend**
- FastAPI backend + PostgreSQL + Redis task queue
- OpenRouter for structured requirement parsing
- Meshy API for 3D model generation
- Python geometry worker: mesh repair, normalization, seam planning, unfolding

<!-- [配图占位：架构图 / 前后端分离截图 / API 文档截图] -->

---

## What's Next

- Paper size input is still manual — needs smart presets (A4 / Letter / roll widths)
- The UI flow is long — needs a smoother, more guided experience
- More garment shapes & fabric types
- A Nest & Cut layout optimizer for professionals

---

<!-- _class: lead -->

# Thank You

### Questions?

Plush Pattern Studio
