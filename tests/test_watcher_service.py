from threading import Event

from lsprotocol.types import FileChangeType, FileEvent

from djlsp.services import WatcherService


def test_watcher_service_debounces_and_merges_change_kinds():
    service = WatcherService(debounce_seconds=0.01)
    completed = Event()
    received = []

    def callback(change_kinds):
        received.append(change_kinds)
        completed.set()

    service.schedule_collection(
        callback,
        [
            FileEvent(
                uri="file:///tmp/project/templates/index.html",
                type=FileChangeType.Changed,
            )
        ],
    )
    service.schedule_collection(
        callback,
        [
            FileEvent(
                uri="file:///tmp/project/app/views.py",
                type=FileChangeType.Changed,
            )
        ],
    )

    assert completed.wait(0.5)
    assert received == [{"python", "template"}]


def test_watcher_service_skips_non_actionable_changes():
    service = WatcherService(debounce_seconds=0.01)
    completed = Event()

    service.schedule_collection(
        lambda _change_kinds: completed.set(),
        [
            FileEvent(
                uri="file:///tmp/project/.editorconfig", type=FileChangeType.Changed
            )
        ],
    )

    assert not completed.wait(0.1)
    assert service.collection_scope({"other"}) == "none"
    assert service.collection_scope({"python"}) == "full"
