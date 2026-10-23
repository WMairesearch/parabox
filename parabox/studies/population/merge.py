"""Historical import path for the shared-record merge implementation."""

from parabox.execution.merge import (collect_changes, final_accepted, merge_record,
                                     prefixed_name, snapshot_shared)

__all__ = ["collect_changes", "final_accepted", "merge_record", "prefixed_name", "snapshot_shared"]
