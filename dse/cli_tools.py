"""Command line for My tools and Tool Studio (python dse.py mytool ... / python dse.py studio ...). See dse/mytools.py and dse/studio.py."""
from __future__ import annotations

import sys

from . import mytools, studio


def _opt(args: list[str], name: str, default: str = "") -> tuple[str, list[str]]:
    if name in args:
        i = args.index(name)
        v = args[i + 1] if i + 1 < len(args) else default
        return v, args[:i] + args[i + 2:]
    return default, args


def main(which: str, args: list[str]) -> int:
    try:
        return _mytool(args) if which == "mytool" else _studio(args)
    except ValueError as e:
        print(str(e))
        return 2


def _mytool(a: list[str]) -> int:
    if not a or a[0] in ("-h", "--help"):
        print(mytools.__doc__)
        return 0
    x, rest = a[0], a[1:]
    if x == "list":
        print(mytools.listing())
    elif x == "check":
        print(mytools.check_report(rest[0] if rest else ""))
    elif x == "save":
        shared = "--shared" in rest
        rest = [r for r in rest if r != "--shared"]
        print(mytools.save(rest[0] if rest else "", shared))
    elif x == "run":
        if not rest:
            print("Usage: python dse.py mytool run my.<slug> --in-<name> value")
            return 2
        return mytools.run(rest[0], rest[1:])
    else:
        print(mytools.__doc__)
        return 2
    return 0


def _studio(a: list[str]) -> int:
    if not a or a[0] in ("-h", "--help"):
        print(studio.__doc__)
        return 0
    x, rest = a[0], a[1:]
    if x == "config":
        if "--enable" in rest:
            print(studio.set_enabled(True))
        elif "--disable" in rest:
            print(studio.set_enabled(False))
        else:
            print(f"Tool Studio is {'ON' if studio.enabled() else 'OFF'} on this PC.")
    elif x == "list":
        print(studio.listing())
    elif x == "show":
        print(studio.show(rest[0] if rest else ""))
    elif x == "test":
        print(studio.test(rest[0] if rest else ""))
    elif x == "enable":
        code, rest = _opt(rest, "--approve")
        print(studio.enable(rest[0] if rest else "", code))
    elif x == "disable":
        print(studio.disable(rest[0] if rest else ""))
    elif x == "publish":
        print(studio.publish(rest[0] if rest else ""))
    elif x in ("draft", "revise"):
        if len(rest) < 2:
            print(f"Usage: python dse.py studio {x} <name> \"what it should do\"")
            return 2
        if not studio.enabled():
            print("Tool Studio is off on this PC. Turn it on first: python dse.py studio config --enable")
            return 2
        print((studio.draft if x == "draft" else studio.revise)(rest[0], " ".join(rest[1:])))
    elif x == "run":
        return studio.run(rest[0], rest[1:]) if rest else 2
    else:
        print(studio.__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2:]))
