import json
import os
import sys


def atomic_json(path, data):
    temporary = path + ".lamp.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def update_directory(directory):
    binding_path = os.path.join(directory, "UIRealtimeBindings.json")
    with open(binding_path, "r", encoding="utf-8-sig") as handle:
        bindings = json.load(handle)
    status_count = 0
    for item in bindings.get("statuses", {}).values():
        if not isinstance(item, dict):
            continue
        item.update({
            "operator": "=",
            "threshold": 1.0,
            "on_color": "#ff2020",
            "off_color": "#14d84a",
        })
        status_count += 1
    atomic_json(binding_path, bindings)

    tv_path = os.path.join(directory, "MonitorTVConfig.json")
    with open(tv_path, "r", encoding="utf-8-sig") as handle:
        tv_config = json.load(handle)
    rectangle_count = 0
    for monitor_id in ("G1", "G2"):
        for item in tv_config.get(monitor_id, {}).get("rectangles", {}).values():
            if not isinstance(item, dict):
                continue
            item.update({
                "operator": "=",
                "threshold": 1.0,
                "true_color": "#ff2020",
                "false_color": "#14d84a",
                "on_color": "#ff2020",
                "off_color": "#14d84a",
            })
            rectangle_count += 1
    atomic_json(tv_path, tv_config)
    print(f"{directory}: statuses={status_count}, tv_rectangles={rectangle_count}")


for target_directory in sys.argv[1:]:
    update_directory(os.path.abspath(target_directory))
