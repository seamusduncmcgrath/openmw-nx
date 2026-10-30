#!/usr/bin/env python3
"""Make dialogue keyword matching work for CJK text.

Upstream requires a keyword match to start right after a word separator
(space, quote, bracket...). Chinese text has no spaces, so topic names are
never matched inside dialogue lines, the player never learns any topic and
the topic list stays empty.

The fix is to also allow a match to start at a 3-byte UTF-8 lead byte
(0xE0..0xEF), which is where every CJK character begins.
"""
import io
import os

ROOT = os.getcwd()
CPP = os.path.join(ROOT, "apps", "openmw", "mwdialogue", "keywordsearch.cpp")


def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p, t):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def main():
    if not os.path.exists(CPP):
        raise SystemExit("not found: %s" % CPP)

    t = read(CPP)
    old = ("if (wordSeparators.find(*prev) == std::string_view::npos)\n"
           "                    continue;")
    new = ("if (wordSeparators.find(*prev) == std::string_view::npos\n"
           "                    && static_cast<unsigned char>(*i) < 0xe0) // CJK: allow any 3-byte utf-8 char\n"
           "                    continue;")

    if new in t:
        print("already patched")
        return
    if t.count(old) != 1:
        raise SystemExit("anchor not found (%d matches) in %s" % (t.count(old), CPP))
    t = t.replace(old, new, 1)
    write(CPP, t)
    print("patched:", CPP)


if __name__ == "__main__":
    main()
