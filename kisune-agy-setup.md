# Kisune dev-workflow Skills in Antigravity CLI (agy)

This document covers installing the [kisune dev-workflow skills](https://github.com/xbklairith/kisune/tree/main/dev-workflow)
into Antigravity CLI, replacing the Claude Code–specific slash commands with equivalent agy workflows.

---

## Background: What Transfers and What Does Not

The kisune `dev-workflow` plugin has four distinct types of artifacts:

| Artifact | Claude Code | Transfers to agy? | Notes |
|---|---|---|---|
| `skills/` (15 skill dirs, each with `SKILL.md`) | Skill tool invocation | ✅ Yes — natively | Already in standard `SKILL.md` format |
| `commands/spec.md` and `commands/spec/*.md` | `/dev-workflow:spec` slash command | ❌ No direct equivalent | Replaced by natural-language prompts (see §4) |
| `hooks/` | Pre/post-tool hooks | ❌ No equivalent | Not needed for spec workflow |
| `AGENTS.md` | Project constitution / system context | ✅ Partial | Merge into your repo's `AGENTS.md` |

---

## Part 1 — Global Installation (All Projects)

Global skills are stored in `~/.gemini/antigravity/skills/` and are available across every workspace.

> **Known quirk:** On some agy versions the global skills folder must be named `global_skills` instead of `skills`.
> If skills are not detected after step 3, rename the directory as shown in step 1b.

### Step 1 — Clone the kisune repository

```bash
git clone https://github.com/xbklairith/kisune.git ~/kisune
```

### Step 1b — Create the global skills directory

```bash
# Standard path (works on most systems)
mkdir -p ~/.gemini/antigravity/skills

# If skills are not detected later, use this name instead:
# mkdir -p ~/.gemini/antigravity/global_skills
```

### Step 2 — Symlink each skill subdirectory

Symlink individual skill directories so a future `git pull` in `~/kisune` keeps them up to date.

```bash
for skill in ~/kisune/dev-workflow/skills/*/; do
  skill_name=$(basename "$skill")
  ln -sfn "$skill" ~/.gemini/antigravity/skills/"$skill_name"
done
```

### Step 3 — Verify discovery inside agy

Start an agy session and run:

```
/skills list
```

You should see all 15 kisune skills listed (brainstorming, completion-validation, explain-in,
git-workflow, post-mortem, review, scrutinize, security-review, skill-maker, spawn-agents,
spec-driven-implementation, spec-driven-planning, spec-review, systematic-debug,
test-driven-development, using-kisune).

If the list is empty, try `/skills reload` first. If still empty, rename the folder:

```bash
mv ~/.gemini/antigravity/skills ~/.gemini/antigravity/global_skills
```

Then restart agy and run `/skills list` again.

---

## Part 2 — Project-Level Installation (Specific Repository)

Add skills at the project level when you want them scoped to a single workspace (e.g. your
`app.litkovskyi.de` repo) and committed to version control so other contributors share them.

> If you already have global skills installed, project-level installation is **optional** — the same
> skills are available globally. Install at project level when you want the repo to be self-contained
> or when you share it with collaborators.

### Step 1 — Create the project skills directory

Run from the repo root:

```bash
mkdir -p .agents/skills
```

> agy also accepts `.agent/skills` (legacy). The canonical current path is `.agents/skills`.

### Step 2 — Symlink or copy skills into the project

**Option A — Symlink (recommended for solo use; requires `~/kisune` on each machine):**

```bash
for skill in ~/kisune/dev-workflow/skills/*/; do
  skill_name=$(basename "$skill")
  ln -sfn "$skill" .agents/skills/"$skill_name"
done
```

**Option B — Copy (recommended for teams and CI; self-contained):**

```bash
cp -r ~/kisune/dev-workflow/skills/* .agents/skills/
```

If you copy, add an update script to your project:

```bash
# update-kisune-skills.sh
cp -r ~/kisune/dev-workflow/skills/* .agents/skills/
git add .agents/skills/
git commit -m "chore: update kisune dev-workflow skills"
```

### Step 3 — Trust the workspace in agy

Project-level skills only load from a trusted workspace. Inside an agy session:

```
/trust
```

Then restart the session. Run `/skills list` to confirm.

### Step 4 — Gitignore or commit

**To commit skills (Option B copy):** add `.agents/skills/` to version control normally.

**To ignore symlinks (Option A):** add to `.gitignore`:

```
.agents/skills/
```

---

## Part 3 — Updating Skills

```bash
# Pull latest kisune changes
cd ~/kisune && git pull

# If you used Option B (copy) for project-level:
./update-kisune-skills.sh
```

Global symlinks update automatically with the `git pull` — no further action needed.

---

## Part 4 — Replacing the Claude Code `/spec` Command with agy Prompts

The `/dev-workflow:spec` slash command and its sub-commands (`create`, `requirements`, `design`,
`tasks`, `execute`, `review`, `list`) are Claude Code–only extension points. In agy, invoke
the same workflows by explicitly activating skills with natural language. agy discovers and
activates skills automatically when your description matches the skill's purpose.

### Quick reference: command → prompt mapping

| Claude Code command | agy equivalent prompt |
|---|---|
| `/dev-workflow:spec` (interactive menu) | `Show me the spec-driven development menu. Use @spec-driven-planning skill.` |
| `/dev-workflow:spec "feature-name"` | `Start spec-driven planning for the feature "feature-name". Auto-pick Quick or Full mode.` |
| `/dev-workflow:spec quick "feature-name"` | `Start spec-driven planning for "feature-name" in Quick mode (single plan.md).` |
| `/dev-workflow:spec full "feature-name"` | `Start spec-driven planning for "feature-name" in Full mode (requirements + design + tasks, EARS format).` |
| `/dev-workflow:spec requirements` | `Generate the requirements document for the current feature in Full mode using EARS format.` |
| `/dev-workflow:spec design` | `Generate the technical design document for the current feature in Full mode.` |
| `/dev-workflow:spec tasks` | `Break down the current Full-mode feature spec into TDD implementation tasks.` |
| `/dev-workflow:spec execute` | `Execute the implementation for the current feature. Auto-detect Quick (plan.md) or Full (tasks.md) mode.` |
| `/dev-workflow:spec review "feature-name"` | `Review the spec for "feature-name" across all 6 dimensions: business, correctness, completeness, compatibility, traceability, and testability. Use @spec-review skill.` |
| `/dev-workflow:spec list` | `List all features in docx/features/ with their mode (Quick/Full) and current status.` |

### Activating skills explicitly

If agy does not auto-activate a skill from the natural-language trigger, explicitly reference it:

```
Use the @spec-driven-planning skill to start Full-mode planning for "pdf-statement-import".
```

```
Activate @spec-review and review the "moneywiz-import" feature specification.
```

### Spec workflow cheat sheet

Below is the full end-to-end sequence for a new Full-mode feature, using agy-compatible prompts:

```
1. "Plan a new feature called 'reconciliation-override' in Full mode using @spec-driven-planning."

2. "Generate EARS-format requirements for 'reconciliation-override' using @spec-driven-planning."

3. "Generate the technical design for 'reconciliation-override' using @spec-driven-planning."

4. "Break 'reconciliation-override' into TDD implementation tasks using @spec-driven-implementation."

5. "Execute implementation for 'reconciliation-override' using @spec-driven-implementation."

6. "Review the complete spec for 'reconciliation-override' across all 6 dimensions using @spec-review."
```

---

## Part 5 — Adding This Document to agy Context

To give agy persistent awareness of this setup guide and the kisune workflow conventions, add
this file to your `AGENTS.md` or reference it directly in agy sessions.

### Option A — Reference in AGENTS.md (recommended)

Append the following block to the root `AGENTS.md` of your project:

```markdown
## Dev-Workflow Skills (kisune)

Spec-driven development uses the kisune dev-workflow skills installed at `.agents/skills/`.
Full installation and usage reference: `.agents/kisune-agy-setup.md`.

Key skills available:
- `spec-driven-planning` — Feature planning (Quick and Full mode)
- `spec-driven-implementation` — TDD task breakdown and execution
- `spec-review` — 6-dimension parallel spec review
- `systematic-debug` — Structured debugging
- `git-workflow` — Commit and branch conventions
- `security-review` — Security audit
- `test-driven-development` — TDD workflow

To start any spec workflow: "Use @spec-driven-planning to plan feature X."
Full command-to-prompt mappings: see `.agents/kisune-agy-setup.md §4`.
```

### Option B — Copy this file into the project skills directory

```bash
cp kisune-agy-setup.md .agents/kisune-agy-setup.md
```

Then reference it in a session:

```
Read .agents/kisune-agy-setup.md to understand how to use kisune skills in this project.
```

### Option C — Add as a global skill

Create a wrapper skill so agy can always answer questions about this setup:

```bash
mkdir -p ~/.gemini/antigravity/skills/kisune-setup
cp kisune-agy-setup.md ~/.gemini/antigravity/skills/kisune-setup/SKILL.md
```

> Note: The file must be named exactly `SKILL.md` (case-sensitive on Linux/macOS) for agy to
> discover it. You may need to add a short front-matter description at the top of the file if
> agy requires it for activation matching.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/skills list` shows nothing | Wrong folder name | Rename to `global_skills` (see §1 step 1b) |
| Project skills not loading | Workspace not trusted | Run `/trust` and restart session |
| Skill not auto-activated | Description mismatch | Use explicit `@skill-name` reference |
| Symlink skills not found | Symlinks not followed | Use `cp -r` (Option B) instead |
| `SKILL.md` not discovered | Nested more than 1 level deep | Each skill must be exactly `skills/<name>/SKILL.md` |
