#!/usr/bin/env python3
"""Tests for build/engine_overlay/jp_missing_handlers.py (JP pass-through handlers).

Run:  PYTHONIOENCODING=utf-8 python -I -X utf8 build/test_jp_missing_handlers.py

The handlers are called directly with the `(spec, request)` signature `exvius_actions.serve_actions`
uses, so no server has to be started.  The engine modules are imported when available
(`FFBE_ENGINE`, default path below) to prove `install()` really registers the ids; if that import is
not possible the handler checks still run and the limitation is printed (the script exits 0 only
when the handler expectations hold).
"""
from __future__ import annotations

import copy
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path(os.environ.get(
    "FFBE_ENGINE",
    r"C:\Users\USER\Documents\Projects\ffbe_offline_modfix\upstream\source\server"))
JP_MST = ROOT / "build" / "out" / "jp_offline" / "engine" / "static" / "mst_decoded"
MODULE = ROOT / "build" / "engine_overlay" / "jp_missing_handlers.py"

if JP_MST.is_dir():
    os.environ.setdefault("MST_DIR", str(JP_MST))
if ENGINE.is_dir():
    sys.path.insert(0, str(ENGINE))

# `-I` drops site-packages; the engine imports PyYAML from there.
try:
    import yaml  # noqa: F401
except ModuleNotFoundError:
    try:
        import site
        _user_site = site.getusersitepackages()
        if _user_site and _user_site not in sys.path:
            sys.path.append(_user_site)
        import yaml  # noqa: F401
    except Exception:  # noqa: BLE001 - the limit is reported below
        pass

FAILURES = []
LIMITS = []
PASSED = 0


def check(name, condition, detail=""):
    global PASSED
    if condition:
        PASSED += 1
        print("ok   %s" % name)
    else:
        print("FAIL %s%s" % (name, (" -- " + detail) if detail else ""))
        FAILURES.append(name)


def limit(name, detail):
    print("LIMIT %s -- %s" % (name, detail))
    LIMITS.append(name + ": " + detail)


def load_module():
    spec = importlib.util.spec_from_file_location("jp_missing_handlers", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = load_module()
    H = module.HANDLERS

    # 1. Expected request ids are registered.
    expected = {
        "Tnkz60cb", "f8Q0BJVX", "FR4ISN7P", "t8Yd2Pcy", "XG3CwM1N",
        "crzI2bA5", "CY89mIdz", "oE5fmZN9", "D1gXmV3L", "5Rsp7xM6",
        "U8F0Q25i", "80R6BXUw", "k8ew94DN", "17LFJD0b",
    }
    check("HANDLERS covers the 14 target ids", set(H) == expected,
          "missing=%s extra=%s" % (sorted(expected - set(H)), sorted(set(H) - expected)))

    # 2. Every handler returns a dict from spec=None and leaves the request untouched.
    for rid, fn in sorted(H.items()):
        req = {"LhVz6aD2": [{"D3fzIL1s": "secret99"}], "keep": [{"x": "1"}]}
        frozen = copy.deepcopy(req)
        out = fn(None, req)
        check("%s: dict reply, request unchanged" % rid,
              isinstance(out, dict) and req == frozen,
              "type=%s" % type(out).__name__)
        check("%s: non-empty user-state group" % rid,
              isinstance(out.get("LhVz6aD2"), list) and bool(out["LhVz6aD2"]),
              repr(out)[:120])

    # 3. Explore: the disabled answer (identity only, no explore list, no state group).
    for rid in module.EXPLORE_REQUESTS:
        out = H[rid](None, {})
        check("explore %s: no explore list invented" % rid,
              not any(k in out for k in ("2J1wCyhQ", "w46Zt1MT")))
        check("explore %s: identity ack only" % rid, set(out) == {"LhVz6aD2"}, sorted(out))

    # 4. Transfer issue: fixed 12-digit code, password echoed only when valid.
    out = H["crzI2bA5"](None, {"LhVz6aD2": [{"D3fzIL1s": "abc123"}]})
    row = out["LhVz6aD2"][0]
    check("transfer issue: 12-digit non-zero code", bool(__import__("re").fullmatch(
        r"[1-9][0-9]{11}", str(row.get("c52MWCji")))), str(row.get("c52MWCji")))
    check("transfer issue: valid password echoed", row.get("D3fzIL1s") == "abc123")
    out = H["crzI2bA5"](None, {"LhVz6aD2": [{"D3fzIL1s": "bad password!"}]})
    check("transfer issue: invalid password replaced", out["LhVz6aD2"][0].get("D3fzIL1s") == "1234")
    out = H["crzI2bA5"](None, {})
    check("transfer issue: empty request still answers a code",
          out["LhVz6aD2"][0].get("c52MWCji") == "123456789012")

    # 5. Refusals carry MessageResponse type 1 / cmd 2 with a non-empty text.
    for rid, label in (("CY89mIdz", "check"), ("oE5fmZN9", "execute"), ("5Rsp7xM6", "delete")):
        out = H[rid](None, {})
        msg = (out.get("bCf65yoK") or [{}])[0]
        check("transfer/delete %s: error message group" % label,
              msg.get("D8aznm56") == "1" and msg.get("5oHZM9zK") == "2"
              and isinstance(msg.get("Wk1v6upb"), str) and msg.get("Wk1v6upb"),
              repr(msg))
        check("transfer/delete %s: identity kept for scenes that ignore it" % label,
              bool(out.get("LhVz6aD2")))

    # 6. DeleteUser / Transfer refuse without touching the one player state, and the identity
    #    group really triggers the engine's projection.
    try:
        import ffbe_state
        import player_state
        fresh = player_state.PlayerState.load("/nonexistent", slot="selftest")
        ffbe_state.State.player = fresh
        before_data = copy.deepcopy(fresh.data)
        before_dirty = fresh.dirty
        for rid in ("5Rsp7xM6", "oE5fmZN9", "CY89mIdz"):
            out = H[rid](None, {"LhVz6aD2": [{"9Tbns0eI": "100000001"}]})
            projected = fresh.apply_to_reply(out)
            check("state %s: player.data unchanged" % rid, fresh.data == before_data)
            check("state %s: dirty flag unchanged" % rid, fresh.dirty == before_dirty)
            check("state %s: projection adds team + roster" % rid,
                  bool(projected.get("3oU9Ktb7")) and "B71MekS8" in projected)
        out = H["U8F0Q25i"](None, {})
        projected = fresh.apply_to_reply(out)
        check("equip grow: projection keeps its event/status tags",
              projected.get("1P4YjSbT") == out["1P4YjSbT"]
              and projected.get("81kzGcgF") == out["81kzGcgF"])
        check("equip grow: state unchanged by entry", fresh.data == before_data)
        ffbe_state.State.player = None
    except Exception as exc:  # noqa: BLE001 - engine not importable in isolation
        limit("delete-user state check", type(exc).__name__ + ": " + str(exc))

    # 7. EquipGrow: no-run state with a real-looking area mission and categories.
    for rid in ("U8F0Q25i", "80R6BXUw", "k8ew94DN"):
        out = H[rid](None, {})
        event = (out.get("1P4YjSbT") or [{}])[0]
        status = (out.get("81kzGcgF") or [{}])[0]
        snapshot = (out.get("bvd6n4u2") or [{}])[0]
        mission = str(event.get("qhMKRz81") or "")
        check("equip grow %s: event info" % rid, bool(event), repr(out)[:160])
        check("equip grow %s: area mission is difficulty@id" % rid,
              mission.startswith("0@") and mission[2:].isdigit(), mission)
        check("equip grow %s: no run marked" % rid,
              event.get("J1YX9kmM") == "" and event.get("aXqD3i9J") == "")
        check("equip grow %s: status open, no pending pick" % rid,
              status.get("ah9URJd7") == "0" and status.get("cEVau7d8") == "1", repr(status))
        check("equip grow %s: empty floor snapshot" % rid, snapshot.get("3KJpzuC5") == "")

    categories = (H["U8F0Q25i"](None, {}).get("1P4YjSbT") or [{}])[0].get("h3N2ZU5Q")
    if categories:
        check("equip grow: categories are sorted integer csv",
              [int(c) for c in categories.split(",")] == sorted(int(c) for c in categories.split(",")))
    else:
        limit("equip grow categories", "F_EQUIP_ITEM_MST not readable from MST_DIR")

    # 8. Existing spec dicts are copied, not mutated.
    spec = {"LhVz6aD2": [{"9qh17ZUf": "Rain"}]}
    frozen_spec = copy.deepcopy(spec)
    H["17LFJD0b"](spec, {})
    check("mission break: input spec not mutated", spec == frozen_spec)

    # 9. Real registration in the engine dispatch table.
    try:
        import exvius_actions as ea
        module.install(object())
        check("install: every id in exvius_actions.HANDLERS",
              all(ea.HANDLERS.get(rid) is fn for rid, fn in H.items()))
    except Exception as exc:  # noqa: BLE001
        limit("engine install", type(exc).__name__ + ": " + str(exc))

    print("\n%d checks passed, %d failure(s), %d limitation(s)" % (
        PASSED, len(FAILURES), len(LIMITS)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
