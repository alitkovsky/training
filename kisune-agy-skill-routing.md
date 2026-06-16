# Skill Auto-Selection and Routing in Antigravity CLI

A guide to how agy discovers and activates kisune dev-workflow skills, and how to configure
`AGENTS.md` so the right skill is consistently used without requiring explicit `@skill-name`
invocations on every prompt.

---

## How agy Handles Skills by Default

When a session starts, agy reads the **frontmatter `description` field** from every installed
`SKILL.md` and builds an index of available skills. On each prompt, the model matches the
request context against those descriptions and activates the most relevant skill automatically —
you do not need to invoke it manually in the typical case.

The activation pipeline per prompt is:

```
Prompt received
  → Agent reads AGENTS.md (global rules + session context)
  → Agent scans skill metadata (name + description frontmatter)
  → Agent selects best-matching skill(s) and reads their SKILL.md
  → Agent responds
```

So, adding an explicit routing rule in `AGENTS.md` is **not strictly necessary** — agy will
auto-match skills when the description is accurate. However, auto-matching has two real-world
failure modes that matter for a structured workflow like kisune:

1. **Weak description signals** — the model picks a plausible skill but not the right one
   (e.g., it might use `review` instead of `spec-review` for a spec review task).
2. **No proactive suggestion** — when the prompt is ambiguous, agy silently picks one skill
   and proceeds rather than confirming its choice with you.

Adding a routing rule in `AGENTS.md` addresses both by instructing the agent to surface its
skill selection decision before executing.

---

## Recommended Approach: AGENTS.md Routing Rule

Rather than a rigid "ask before every prompt" rule (which adds friction on simple tasks),
use a **targeted routing rule** that fires only when the prompt is task-type-ambiguous or
touches one of the kisune workflow entry points. This keeps fluent one-shot tasks fast while
making the high-stakes spec/review/debug decisions explicit.

Add the following block to your project's `AGENTS.md`:

```markdown
## Skill Routing (kisune dev-workflow)

Before beginning any task that involves planning, specification, review, debugging,
or a multi-step workflow, do the following:

1. Identify the best-matching kisune skill from the installed list:
   - Planning / spec writing → `spec-driven-planning`
   - Breaking down tasks / implementation → `spec-driven-implementation`
   - Reviewing a spec → `spec-review`
   - Debugging → `systematic-debug`
   - Git operations → `git-workflow`
   - Security audit → `security-review`
   - TDD → `test-driven-development`
   - Code review → `review`
   - Brainstorming → `brainstorming`
   - Scrutinizing a decision or design → `scrutinize`
   - Spawning parallel agents → `spawn-agents`
   - Completion check → `completion-validation`
   - Creating a new skill → `skill-maker`

2. Before executing, state in one sentence:
   "I'll use **@skill-name** for this task — [one-line reason]."
   Then wait for confirmation or a correction before proceeding.

3. If no kisune skill clearly applies, say so and proceed with your default behaviour.

This rule applies to planning, spec, review, debug, and multi-step tasks only.
For simple code edits, one-liner questions, and direct lookups, proceed without confirmation.
```

This gives you a clear, low-friction contract: agy announces its skill choice for complex
tasks, you can override it with a single word ("use spec-review instead"), and simple tasks
flow uninterrupted.

---

## Why Not "Ask Before Every Prompt"?

Requiring skill confirmation on every prompt has a real cost:

| Approach | Benefit | Downside |
|---|---|---|
| Confirm every prompt | Maximum visibility | Adds a round-trip to every quick question, slows iteration |
| Targeted routing (recommended above) | Covers all high-stakes decisions | Very rare false negative on truly ambiguous one-liners |
| Fully automatic (default agy behaviour) | Zero friction | Silent wrong-skill selection is hard to catch |

The targeted approach is the right balance for a spec-driven project like your finance app,
where the kisune workflow phases (planning → requirements → design → tasks → implement → review)
are distinct and the cost of being in the wrong phase is high.

---

## Skill Description Quality Matters

Auto-matching works entirely off the `description` field in each `SKILL.md` frontmatter. If a
skill's description is vague, the model will under-activate it. You can inspect the
descriptions of your installed kisune skills and strengthen any that are weak:

```bash
# Print name + description frontmatter for all project-level skills
for skill in .agents/skills/*/SKILL.md; do
  echo "=== $skill ==="
  awk '/^---/{p++} p==1' "$skill" | grep -E "^(name|description):"
  echo ""
done
```

If a skill is repeatedly missed, open its `SKILL.md`, find the `description:` line, and
rewrite it to include the specific trigger phrases you use in practice. For example:

```yaml
# Before (vague):
description: Helps with code review.

# After (trigger-rich):
description: >
  Use when reviewing a feature spec, evaluating a pull request, auditing code quality,
  or when asked to "review", "check", "inspect", or "evaluate" a design or implementation.
```

---

## Global vs. Project AGENTS.md Placement

| File | Scope | When to use |
|---|---|---|
| `~/.gemini/antigravity/AGENTS.md` | All projects | Rules that apply to every workspace |
| `<repo-root>/AGENTS.md` | This project only | Project-specific routing, stack rules |

For the kisune routing rule above:
- If you plan to use kisune in all your projects → add to `~/.gemini/antigravity/AGENTS.md`.
- If kisune is specific to this finance app → add to the project root `AGENTS.md` only.

You can nest `AGENTS.md` files — agy merges them, with the project-level file taking
precedence for any conflicting rules.

---

## Companion Skill: `using-kisune`

The kisune plugin ships a meta-skill called `using-kisune` specifically for this purpose. It
contains a decision flowchart that maps task types to the right kisune skill. You can reference
it directly in the routing rule:

```markdown
## Skill Routing (kisune dev-workflow)

Before any planning, spec, review, or debug task, read `@using-kisune` to identify the
correct skill, then announce your selection and wait for confirmation before proceeding.
```

This delegates the routing logic entirely to the kisune meta-skill rather than duplicating
the decision table in `AGENTS.md`, which keeps the project constitution leaner.

---

## Full AGENTS.md Addition (Copy-Paste Ready)

Append this block to your existing project `AGENTS.md`:

```markdown
## Dev-Workflow Skills (kisune)

Kisune skills are installed at `.agents/skills/`. The full setup reference is at
`.agents/kisune-agy-setup.md`.

### Skill Routing

For planning, specification, review, debugging, or any multi-step workflow task:

1. Read `@using-kisune` to identify the correct skill, OR match manually:
   - Planning / spec writing       → `@spec-driven-planning`
   - Task breakdown / implement    → `@spec-driven-implementation`
   - Reviewing a spec              → `@spec-review`
   - Debugging                     → `@systematic-debug`
   - Git operations                → `@git-workflow`
   - Security audit                → `@security-review`
   - TDD                           → `@test-driven-development`
   - Code review                   → `@review`
   - Brainstorming                 → `@brainstorming`
   - Scrutinizing a decision       → `@scrutinize`
   - Parallel agent work           → `@spawn-agents`
   - Completion validation         → `@completion-validation`
   - Creating a new skill          → `@skill-maker`

2. Before executing, state: "I'll use **@skill-name** — [reason]." and wait for confirmation.

3. For simple edits, lookups, and quick questions: proceed without confirmation.
```
