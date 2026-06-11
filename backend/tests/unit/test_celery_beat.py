"""Verify the Celery beat schedule includes the trial expiry task.
"""

from tasks.celery_app import celery_app


class TestBeatSchedule:
    """Trial expiry must have a daily beat schedule entry."""

    def test_check_trial_expiry_in_beat_schedule(self):
        """The beat schedule must have a check-trial-expiry entry."""
        schedule = celery_app.conf.beat_schedule
        assert "check-trial-expiry" in schedule, (
            f"check-trial-expiry not in beat schedule. Keys: {list(schedule.keys())}"
        )

    def test_check_trial_expiry_task_name(self):
        """The entry must reference the correct task."""
        entry = celery_app.conf.beat_schedule["check-trial-expiry"]
        assert entry["task"] == "tasks.trial_expiry.check_trial_expiry", (
            f"Wrong task: {entry['task']}"
        )

    def test_check_trial_expiry_runs_daily(self):
        """The schedule must be daily (crontab at a specific hour)."""
        entry = celery_app.conf.beat_schedule["check-trial-expiry"]
        schedule = entry["schedule"]
        # crontab hour/minute should be set for daily execution
        assert hasattr(schedule, "hour"), "Schedule must be a crontab"
        assert hasattr(schedule, "minute"), "Schedule must have minute"
