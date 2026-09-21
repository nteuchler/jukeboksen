import threading

from simple_jukebox.nfc import NfcReader
from simple_jukebox.services import JukeboxServices
from simple_jukebox.state_machine import StateMachine
from simple_jukebox.tests.test_state_machine import FakePlayer, FakeBluetooth, UnusedService


def test_tags_trigger_once_until_removed_or_replaced():
    reader = NfcReader()
    for uid in [b'\x01\xab', b'\x01\xab', None, b'\x01\xab', b'\x02']:
        reader._record(uid)
    assert reader.status()['detections'] == 3
    assert reader.status()['last_uid'] == '02'
    reader._record(None)
    assert reader.status()['uid'] is None
    assert reader.status()['last_uid'] == '02'


def test_worker_reads_and_releases_device_on_exit():
    scanned = threading.Event()
    cleaned = threading.Event()

    class Device:
        def read_passive_target(self, timeout):
            scanned.set()
            return b'\x12\x34'

    reader = NfcReader(lambda: (Device(), cleaned.set), interval=0.01)
    reader.start()
    assert scanned.wait(1)
    reader.stop()
    assert cleaned.is_set()
    assert not reader.status()['active']
    assert not reader._thread.is_alive()


def test_missing_hardware_reports_error_and_can_stop():
    failed = threading.Event()

    def factory():
        failed.set()
        raise OSError('Reader missing')

    reader = NfcReader(factory)
    reader.start()
    assert failed.wait(1)
    reader.stop()
    assert reader.status()['error'] == 'Reader missing'
    assert not reader.status()['connected']


def test_nfc_mode_lifecycle_and_audio_cleanup():
    class Reader:
        active = False
        def start(self):
            self.active = True
        def stop(self):
            self.active = False
        def status(self):
            return {'active': self.active}

    reader = Reader()
    player = FakePlayer()
    machine = StateMachine(JukeboxServices(player, FakeBluetooth(),
                           UnusedService(), UnusedService(), reader))
    machine.change_mode('local_files')
    machine.play('song.mp3')
    machine.change_mode('nfc')
    assert not player.playing
    assert machine.status()['nfc']['active']
    machine.change_mode('bluetooth')
    assert not reader.active
    machine.change_mode('nfc')
    machine.close()
    assert not reader.active
    assert machine.status()['mode'] == 'idle'


def test_nfc_oled_displays_uid_and_errors():
    from simple_jukebox.oled import status_lines
    lines = status_lines({'mode': 'nfc', 'nfc': {'uid': '1234', 'last_uid': '1234'}})
    assert lines[:3] == ['NFC reader', 'Tag detected', '1234']
    assert 'missing' in status_lines({'mode': 'nfc', 'nfc': {'error': 'missing'}})


def test_web_can_select_nfc_mode():
    from simple_jukebox.tests.test_web import make_app
    app = make_app()
    reader = app.config['services'].nfc
    reader._factory = lambda: (_ for _ in ()).throw(OSError('test reader absent'))
    try:
        response = app.test_client().post('/api/mode', json={'mode': 'nfc'})
        assert response.status_code == 200
        assert response.json['status']['mode'] == 'nfc'
        assert response.json['status']['nfc']['active']
    finally:
        app.config['engine'].close()
        app.config['oled'].stop()
        app.config['input_service'].stop()
