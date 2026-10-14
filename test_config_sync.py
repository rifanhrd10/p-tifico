import contextlib
import importlib.util
import io
import json
import os
import tempfile


SOURCE = os.path.join(os.path.dirname(__file__), "SCADA_BONT_V50_FIELD_MAP (2) - RR FIXNEW01.py")
with contextlib.redirect_stdout(io.StringIO()):
    spec = importlib.util.spec_from_file_location("scada_sync_test_module", SOURCE)
    scada = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scada)


active = {"ip": "10.100.163.150"}
scada._local_scada_ip = lambda: active["ip"]
scada._communication_config = lambda: {
    "master_ip": "10.100.163.150",
    "peer_ip": "10.100.163.149",
    "relay_port": 5001,
    "relay_token": "test-token",
}


def select(directory, ip):
    active["ip"] = ip
    scada.APP_DIR = directory
    scada.CONFIG_SYNC_STATE_PATH = os.path.join(directory, "ConfigSyncState.json")


def write_binding(directory, marker):
    with open(os.path.join(directory, "UIRealtimeBindings.json"), "w", encoding="utf-8") as handle:
        json.dump({"variables": {"marker": marker}, "statuses": {}}, handle)


def read_marker(directory):
    with open(os.path.join(directory, "UIRealtimeBindings.json"), "r", encoding="utf-8") as handle:
        return json.load(handle)["variables"]["marker"]


with tempfile.TemporaryDirectory() as temp:
    pc1 = os.path.join(temp, "pc1")
    pc2 = os.path.join(temp, "pc2")
    os.mkdir(pc1)
    os.mkdir(pc2)
    write_binding(pc1, "pc1-initial")
    write_binding(pc2, "pc2-initial")

    select(pc1, "10.100.163.150")
    pc1_initial = scada._config_sync_snapshot()
    select(pc2, "10.100.163.149")
    scada._config_sync_snapshot()
    assert scada._apply_config_sync_snapshot(pc1_initial) == ["UIRealtimeBindings.json"]
    assert read_marker(pc2) == "pc1-initial"

    # PC2 -> PC1
    write_binding(pc2, "edited-on-pc2")
    pc2_update = scada._config_sync_snapshot()
    select(pc1, "10.100.163.150")
    assert scada._apply_config_sync_snapshot(pc2_update) == ["UIRealtimeBindings.json"]
    assert read_marker(pc1) == "edited-on-pc2"

    # PC1 -> PC2
    write_binding(pc1, "edited-on-pc1")
    pc1_update = scada._config_sync_snapshot()
    select(pc2, "10.100.163.149")
    assert scada._apply_config_sync_snapshot(pc1_update) == ["UIRealtimeBindings.json"]
    assert read_marker(pc2) == "edited-on-pc1"

    # Simultaneous edits converge deterministically instead of ping-ponging.
    write_binding(pc2, "pc2-conflict")
    pc2_conflict = scada._config_sync_snapshot()
    select(pc1, "10.100.163.150")
    write_binding(pc1, "pc1-conflict")
    pc1_conflict = scada._config_sync_snapshot()
    select(pc2, "10.100.163.149")
    scada._apply_config_sync_snapshot(pc1_conflict)
    select(pc1, "10.100.163.150")
    scada._apply_config_sync_snapshot(pc2_conflict)
    assert read_marker(pc1) == "pc1-conflict"
    assert read_marker(pc2) == "pc1-conflict"

print("CONFIG_SYNC_TEST_OK: PC1<->PC2, persistence, conflict convergence")


class LampHarness:
    ui_bindings = {
        "statuses": {
            "lamp": {
                "Source_Kind": "rectangle_status_csv",
                "operator": "<",
                "threshold": 999,
                "on_color": "#000000",
                "off_color": "#ffffff",
            }
        }
    }

    def _record_rectangle_transition(self, *_args):
        pass


lamp = LampHarness()
style = scada.SCADAMainUI._status_rectangle_style
assert style(lamp, "lamp", 0, True) == (False, "#14d84a")
assert style(lamp, "lamp", 1, True) == (False, "#14d84a")
assert style(lamp, "lamp", 2, False) == (True, "#ff2020")
assert style(lamp, "lamp", 3, False) == (True, "#ff2020")
print("STATUS_LAMP_TEST_OK: RAW 0/1 green, RAW 2/3 red")
