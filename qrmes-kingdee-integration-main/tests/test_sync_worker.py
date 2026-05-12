from qrmes_kingdee_integration.storage.sqlite_store import SQLiteSyncStore
from qrmes_kingdee_integration.sync.worker import SyncWorker


class FakeService:
    def __init__(self):
        self.pulls = 0
        self.processed = 0

    def sync_from_kingdee(self, **kwargs):
        self.pulls += 1

    def process_pending_changes(self, limit=100):
        self.processed += 1


def test_sync_worker_runs_pull_and_queue_processing(tmp_path):
    store = SQLiteSyncStore(tmp_path / 'kingdee_sync.db')
    service = FakeService()
    worker = SyncWorker(
        store=store,
        pull_services={'material': service},
        outbound_services={'material': service},
        pull_interval_seconds=1,
    )

    worker.run_once()

    assert service.pulls == 1
    assert service.processed == 1
