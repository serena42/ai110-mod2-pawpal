import pytest
from datetime import time
from models import (
    Task, TaskType, AvailabilityWindow, Owner, Pet, Scheduler, DailyPlan
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def basic_owner():
    """Owner free from 8am to 6pm (10 hours)."""
    owner = Owner("Jordan")
    owner.add_window(time(8, 0), time(18, 0))
    return owner


@pytest.fixture
def tight_owner():
    """Owner free from 8am to 8:30am only (30 minutes)."""
    owner = Owner("Jordan")
    owner.add_window(time(8, 0), time(8, 30))
    return owner


@pytest.fixture
def dog():
    return Pet("Mochi", "dog")


# ---------------------------------------------------------------------------
# Model tests (should pass immediately — no scheduler logic needed)
# ---------------------------------------------------------------------------

def test_availability_window_duration():
    window = AvailabilityWindow(time(8, 0), time(10, 30))
    assert window.duration_minutes() == 150


def test_task_defaults():
    task = Task(TaskType.WALK)
    assert task.duration_minutes == 30
    assert task.frequency == 3
    assert task.priority == 1


def test_task_override():
    task = Task(TaskType.FEEDING, frequency=1, duration_minutes=10)
    assert task.frequency == 1
    assert task.duration_minutes == 10
    assert task.priority == 1  # not overridden, should still be default


def test_mark_complete():
    task = Task(TaskType.WALK)
    assert task.completed is False
    task.mark_complete()
    assert task.completed is True


def test_list_tasks_sorted_by_priority(dog):
    dog.add_task(Task(TaskType.GROOMING))   # priority 3
    dog.add_task(Task(TaskType.WALK))       # priority 1
    dog.add_task(Task(TaskType.ENRICHMENT)) # priority 2
    result = dog.list_tasks()
    priorities = [t.priority for t in result]
    assert priorities == sorted(priorities)


def test_urgency_score_frequency_breaks_priority_tie(basic_owner, dog):
    """Among same-priority tasks, higher frequency should score higher (scheduled first)."""
    # WALK: priority 1, frequency 3 — needs 3 slots, must be scheduled before lower-freq tasks
    # FEEDING: priority 1, frequency 2
    # MEDICATION: priority 1, frequency 1
    dog.add_task(Task(TaskType.MEDICATION))  # p=1, f=1
    dog.add_task(Task(TaskType.FEEDING, frequency=2))   # p=1, f=2
    dog.add_task(Task(TaskType.WALK, frequency=3))      # p=1, f=3
    scheduler = Scheduler(basic_owner, dog)
    ordered = scheduler._sort_by_priority()
    task_types = [t.task_type for t in ordered]
    # Walk (3x) should appear before Feeding (2x) before Medication (1x)
    assert task_types.index(TaskType.WALK) < task_types.index(TaskType.FEEDING)
    assert task_types.index(TaskType.FEEDING) < task_types.index(TaskType.MEDICATION)


# ---------------------------------------------------------------------------
# Scheduler tests (will fail until generate_plan() is implemented)
# ---------------------------------------------------------------------------

def test_tasks_scheduled_when_enough_time(basic_owner, dog):
    dog.add_task(Task(TaskType.WALK))
    dog.add_task(Task(TaskType.FEEDING))
    scheduler = Scheduler(basic_owner, dog)
    plan = scheduler.generate_plan()
    assert isinstance(plan, DailyPlan)
    assert len(plan.scheduled) > 0
    assert len(plan.warnings) == 0


def test_high_priority_scheduled_before_low_priority(basic_owner, dog):
    dog.add_task(Task(TaskType.GROOMING))   # priority 3
    dog.add_task(Task(TaskType.WALK))       # priority 1
    scheduler = Scheduler(basic_owner, dog)
    plan = scheduler.generate_plan()
    task_names = [st.task.task_type for st in plan.scheduled]
    assert task_names.index(TaskType.WALK) < task_names.index(TaskType.GROOMING)


def test_task_dropped_when_no_time(tight_owner, dog):
    dog.add_task(Task(TaskType.WALK))       # 30 min
    dog.add_task(Task(TaskType.FEEDING))    # 15 min
    dog.add_task(Task(TaskType.GROOMING))   # 30 min
    scheduler = Scheduler(tight_owner, dog)
    plan = scheduler.generate_plan()
    total_tasks = sum(t.frequency for t in dog.tasks)
    assert len(plan.scheduled) < total_tasks


def test_warning_generated_when_task_dropped(tight_owner, dog):
    dog.add_task(Task(TaskType.WALK))
    dog.add_task(Task(TaskType.FEEDING))
    dog.add_task(Task(TaskType.GROOMING))
    scheduler = Scheduler(tight_owner, dog)
    plan = scheduler.generate_plan()
    assert len(plan.warnings) > 0


def test_feeding_gap_no_warning(basic_owner, dog):
    """2 feedings in a 10-hour window should be spaced fine — no gap warning."""
    dog.add_task(Task(TaskType.FEEDING, frequency=2))
    plan = Scheduler(basic_owner, dog).generate_plan()
    gap_warnings = [w for w in plan.warnings if "gap" in w.lower() or "feeding" in w.lower()]
    assert len(gap_warnings) == 0


def test_feeding_gap_triggers_warning():
    """2 feedings forced into windows 11 hours apart should generate a gap warning."""
    owner = Owner("Jordan")
    owner.add_window(time(8, 0), time(9, 0))    # 1-hour morning window
    owner.add_window(time(19, 0), time(20, 0))  # 1-hour evening window
    dog = Pet("Mochi", "dog")
    dog.add_task(Task(TaskType.FEEDING, frequency=2))
    plan = Scheduler(owner, dog).generate_plan()
    gap_warnings = [w for w in plan.warnings if "gap" in w.lower() or "feeding" in w.lower()]
    assert len(gap_warnings) > 0


def test_recurring_tasks_spread_across_day(basic_owner, dog):
    """3 walks in a 10-hour day should be spread out, not back-to-back."""
    dog.add_task(Task(TaskType.WALK, frequency=3))
    scheduler = Scheduler(basic_owner, dog)
    plan = scheduler.generate_plan()
    walk_starts = sorted(
        e.start_time.hour * 60 + e.start_time.minute
        for e in plan.scheduled if e.task.task_type == TaskType.WALK
    )
    assert len(walk_starts) == 3
    # Each occurrence should be at least 90 minutes after the previous one.
    for i in range(len(walk_starts) - 1):
        assert walk_starts[i + 1] - walk_starts[i] >= 90


def test_two_pets_no_time_overlap(basic_owner):
    """Tasks for two pets must never occupy the same owner time slot."""
    dog = Pet("Mochi", "dog")
    dog.add_task(Task(TaskType.WALK, frequency=3))
    dog.add_task(Task(TaskType.FEEDING, frequency=2))

    cat = Pet("Luna", "cat")
    cat.add_task(Task(TaskType.FEEDING, frequency=2))
    cat.add_task(Task(TaskType.PLAYTIME))

    basic_owner.add_pet(dog)
    basic_owner.add_pet(cat)

    all_plans = Scheduler(basic_owner, dog).generate_all_plans()

    all_entries = [
        entry
        for plan in all_plans.values()
        for entry in plan.scheduled
    ]

    for i, a in enumerate(all_entries):
        for b in all_entries[i + 1:]:
            a_start = a.start_time.hour * 60 + a.start_time.minute
            a_end   = a.end_time.hour   * 60 + a.end_time.minute
            b_start = b.start_time.hour * 60 + b.start_time.minute
            b_end   = b.end_time.hour   * 60 + b.end_time.minute
            assert not (a_start < b_end and b_start < a_end), (
                f"Overlap: {a.task.name} ({a.start_time}–{a.end_time}) "
                f"and {b.task.name} ({b.start_time}–{b.end_time})"
            )


def test_dependency_respected(basic_owner, dog):
    """Medication depends on Feeding — Feeding must be scheduled first."""
    feeding = Task(TaskType.FEEDING)
    medication = Task(TaskType.MEDICATION, dependencies=[feeding])
    dog.add_task(feeding)
    dog.add_task(medication)
    scheduler = Scheduler(basic_owner, dog)
    plan = scheduler.generate_plan()
    scheduled_types = [st.task.task_type for st in plan.scheduled]
    assert TaskType.FEEDING in scheduled_types
    assert TaskType.MEDICATION in scheduled_types
    assert scheduled_types.index(TaskType.FEEDING) < scheduled_types.index(TaskType.MEDICATION)
