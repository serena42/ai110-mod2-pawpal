# PawPal+ (Module 2 Project)

A rule-based daily pet care planner built with Python and Streamlit.
An owner describes their availability and their pets' care tasks; the scheduler
produces a time-blocked daily plan that respects priority, dependencies, and
recurring-task spacing.

---

## System Overview

### Classes

| Class | Responsibility |
|-------|---------------|
| `TaskType` | Enum of every supported care activity (19 types across walks, feeding, hygiene, enrichment, reptile/fish care) |
| `Task` | A single care activity with duration, frequency, priority, optional time constraints, dependency list, and completion status |
| `AvailabilityWindow` | A contiguous free block in the owner's day (start time → end time) |
| `Owner` | The person caring for the pets; holds availability windows and a list of pets |
| `Pet` | A named animal of a given type; holds a list of Tasks with `add_task()` and `list_tasks()` (sorted by priority) |
| `ScheduledTask` | One occurrence of a Task placed at a specific start/end time, with a human-readable reason |
| `DailyPlan` | The output of a scheduling run: a list of ScheduledTasks and any warning strings |
| `Scheduler` | Accepts an Owner and Pet; `generate_plan()` schedules a single pet, `generate_all_plans()` schedules all pets on the owner sharing a common busy-slot pool |

### Algorithmic features

1. **Composite urgency scoring** _(stretch feature — see Agent Mode note below)_ — instead of sorting by raw priority number, each task receives a weighted urgency score: `(6 - priority) × 10 + frequency × 2 - duration × 0.1`. Priority remains dominant (weight 10 per level), but frequency breaks ties among same-priority tasks — a walk needed 3×/day is harder to fit than medication needed 1×/day and is scheduled first. Duration applies a small penalty so shorter tasks are preferred when all else is equal, since they fit into more gaps and leave larger free blocks. Tasks are then scheduled greedily in descending urgency order; any task that cannot be placed generates a warning.

2. **Priority-first greedy scheduling** — tasks are sorted by urgency score (above) before slot assignment; lower-urgency tasks are dropped when time runs out, and a warning is added to the plan.

3. **Dependency resolution via topological sort** — if Task B depends on Task A, a DFS walk of the dependency graph ensures A is always scheduled before B.

4. **Target-time spacing for recurring tasks** — for a task that repeats N times, the day is divided into N equal intervals and each occurrence is targeted to the start of its interval. `_find_slot` then finds the nearest free slot at or after that target, preventing all occurrences from collapsing to back-to-back.

5. **Gap threshold warnings** — after scheduling, consecutive occurrences of feeding, medication, litter box, and misting tasks are checked against configurable maximum-gap thresholds. Gaps that exceed the threshold produce a human-readable warning in the plan.

6. **Shared busy-slot pool across multiple pets** — `generate_all_plans()` maintains a single list of occupied time slots that is passed into each pet's scheduling run in turn, so no two pets are ever assigned the same owner time slot.

### Agent Mode note — composite urgency scoring (feature 1)

Feature 1 was designed and implemented using Claude Code in Agent Mode. The problem: simple priority sorting left same-priority tasks ordered arbitrarily, so a medication needed once a day could be scheduled before a walk needed three times a day even though the walk is harder to fit. I described the goal to the agent — "break priority ties using frequency and duration" — and asked it to propose a scoring formula, write a failing test first, then implement the method. The agent proposed the weighted formula, flagged that priority needed to remain dominant (otherwise the existing `test_high_priority_scheduled_before_low_priority` would break), and chose the weights (10 per priority level, 2 per frequency occurrence, -0.1 per minute of duration) accordingly. I verified correctness by running all 15 tests and checking manually that Walk (p=1, f=3) scores 53, Feeding (p=1, f=2) scores 52.5, and Grooming (p=3, f=1) scores 29 — the ordering matches intuition.

---

## Data Persistence

Owner configuration (name, availability windows, pets, and tasks) is saved to `pawpal_save.json` and reloaded on demand so settings survive between application runs.

The logic lives in `persistence.py`, which provides:
- `owner_to_dict(owner)` / `dict_to_owner(data)` — serialize/deserialize an `Owner` object tree
- `save(data)` / `load()` — write and read the JSON file
- `save_exists()` — check whether a save file is present

In the **Streamlit app**, a sidebar "Save settings" / "Load settings" button pair captures the current form state into the same JSON format and restores it by rewriting session state and triggering a rerun — so the form repopulates exactly as it was left.

In **`main.py`**, the demo saves Jordan's configuration at the end of the script and immediately reloads it, printing the reconstructed pet list to confirm round-trip fidelity.

### Agent Mode note — persistence layer

This feature required coordinated changes across three files (`persistence.py` new, `app.py` updated, `main.py` updated) with no single obvious place to start. I used Claude Code in Agent Mode to orchestrate the work: described the desired JSON schema, asked the agent to design the module boundary (pure I/O layer vs. session-state helpers inside `app.py`), and had it generate all three file changes in sequence. The key design decision the agent surfaced was to keep `persistence.py` free of Streamlit imports — the session-state ↔ dict translation lives in `app.py` so the persistence module stays testable independently. I verified the round-trip worked by running `main.py` and confirming the reloaded pet names and task counts matched the original.

---

## Advanced Scheduling Logic

Two pieces of complex scheduling logic are implemented and observable in both the CLI demo and the Streamlit UI:

**Priority-based urgency scoring** (`Scheduler._urgency_score`) — tasks are not simply sorted by a priority number. A weighted composite score combines priority level (dominant factor), frequency demand, and duration to determine scheduling order. A walk needed 3×/day outranks medication needed 1×/day even when both have the same priority, because the walk competes harder for slots. This is visible in `main.py` output (the "tasks by priority" block shows urgency order before the schedule is printed) and in the Streamlit UI (the generated plan reflects this ordering).

**Time-blocking to prevent overlapping tasks** (`Scheduler.generate_all_plans`) — a single `shared_busy` list of occupied time slots is passed into each pet's scheduling run in turn. Once a slot is taken by Mochi's walk, Luna's feeding cannot be placed there. In `main.py`, no two rows in the unified schedule share a time range. In the Streamlit UI, multi-pet plans are combined into one time-ordered list with no gaps or overlaps. This behavior is also directly verified by the `test_two_pets_no_time_overlap` test.

---

## Running the demo

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python main.py
```

`main.py` creates one owner (Jordan) with three availability windows, two pets
(Mochi the dog and Luna the cat), and 5 tasks each. It prints each pet's tasks
sorted by urgency score, runs the scheduler, prints a unified time-ordered plan,
marks all tasks complete, then saves the configuration to `pawpal_save.json` and
reloads it to verify the round-trip.

## Running the Streamlit app

```bash
streamlit run app.py
```

Opens a browser UI where you can enter owner availability, pick a pet type,
select and configure tasks, and generate a plan interactively.

## Running the tests

```bash
python -m pytest test_scheduler.py -v
```

All 15 tests should pass. The suite covers:

- `AvailabilityWindow.duration_minutes()` arithmetic
- Task default values and partial overrides
- Task completion (`mark_complete()` flips `completed` flag)
- Task list sorted by priority (`list_tasks()` returns ascending order)
- Urgency score frequency tie-breaking (high-frequency same-priority tasks scheduled first)
- Happy-path scheduling (enough time → all tasks scheduled, no warnings)
- Priority ordering (high-priority task appears before low-priority task)
- Capacity enforcement (too little time → some tasks dropped)
- Warning generation when tasks are dropped
- Feeding gap warning absent when feedings are close together
- Feeding gap warning present when feedings are forced far apart
- Recurring task spacing (3 walks spread ≥ 90 min apart across a 10-hour day)
- Two-pet no-overlap (tasks for different pets never share the same time slot)
- Dependency ordering (Medication always follows Feeding)

---

## AI Reflection

This project was built collaboratively with Claude (claude-sonnet-4-6) throughout
the full design-and-implementation cycle. Here is an honest account of how that
shaped the final result.

### What the AI suggested and I accepted

- **Using a Python `Enum` for `TaskType`** instead of plain strings. AI initially
  thought of tasks as strings; I pointed out that an enum gives autocomplete,
  prevents typos, and makes `dict` lookups safe. It made the code noticeably cleaner.

- **`_TASK_DEFAULTS` as a module-level dict** keyed by `TaskType`. The AI proposed
  this as an alternative to hardcoding defaults inside `__init__`. It keeps all
  default values in one place and makes them easy to scan or extend.

- **Topological sort for dependency resolution**. The scheduler needs to honor
  "Medication must follow Feeding" without the caller specifying an explicit order.
  The AI proposed a DFS visit over the dependency graph inside `_sort_by_priority`.
  I accepted it after tracing through the logic manually.

- **Target-time spacing** to replace a greedy cursor approach. The first version
  of the scheduler scheduled all occurrences of a recurring task back-to-back.
  The AI proposed dividing the day into equal intervals and targeting each
  occurrence to the start of its interval, then finding the nearest free slot.
  This fixed the clustering problem without adding much complexity.

- **`PET_TASK_DEFAULTS`** as a UI-only preset dict (not part of the data model).
  When the AI wanted the app to pre-select sensible tasks for a given pet type, I
  suggested keeping this as a presentation-layer lookup rather than baking
  pet-type logic into the `Pet` or `Task` classes, which kept the model clean.

### What the AI suggested and I rejected or modified

- **An LLM-powered reasoning layer** for explaining scheduling decisions. The AI
  offered this early in the conversation. I rejected it — rule-based logic was the
  right fit for this assignment and far easier to test and reason about.

- **A `TaskTemplate` class** to separate "task definition" from "task instance."
  The AI floated this to handle the case where multiple pets share the same task
  type with different settings. I decided it was over-engineering for a single-pet-
  per-run use case; initializing `Task` with overridable defaults was sufficient.

- **JSON persistence** I suggested this as a natural next step. We deferred it deliberately — the assignment does not require it and adding it would have distracted from the core scheduling logic.

### How correctness was verified

Each algorithmic feature has at least one dedicated test that can fail in a
meaningful way:

- The spacing test (`test_recurring_tasks_spread_across_day`) asserts that each
  consecutive walk is ≥ 90 minutes after the previous one — it would catch any
  regression in the interval calculation.
- The gap warning tests use two fixtures: one where feedings are close (no warning
  expected) and one where two 1-hour windows are 11 hours apart (warning expected).
  Both are needed; the positive case alone is not sufficient.
- The dependency test checks list index ordering, not just presence, ensuring the
  topological sort actually places Feeding before Medication.
- I had to actually run the app to notice some things, like we'd created all of the logic but there was no UI component that let you use the logic (like multiple owners, multiple pets per owner).

The AI flagged that an early version of the gap warning test only covered the
no-warning case, which would pass even if the warning logic were completely broken.
Adding the positive case (`test_feeding_gap_triggers_warning`) was the right call.
