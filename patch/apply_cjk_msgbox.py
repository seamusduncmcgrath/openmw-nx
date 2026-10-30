#!/usr/bin/env python3
"""Pre-wrap CJK text before it reaches the message box EditBox.

MyGUI's EditBox only wraps at whitespace, so a Chinese paragraph has no break
opportunity and runs past the right edge of the message box.

This patch:
  1. adds a helper that inserts an explicit newline every N CJK characters,
  2. uses it for both the plain and the interactive message box.
"""
import io
import os
import re

ROOT = os.getcwd()
CPP = os.path.join(ROOT, "apps", "openmw", "mwgui", "messagebox.cpp")

HELPER = r"""
namespace
{
    // MyGUI wraps on whitespace only; insert explicit breaks for CJK runs
    std::string wrapCJKText(const std::string& text, int maxChars)
    {
        if (maxChars < 6)
            maxChars = 6;

        std::string out;
        out.reserve(text.size() + 32);

        int col = 0;
        for (std::size_t i = 0; i < text.size();)
        {
            const unsigned char c = static_cast<unsigned char>(text[i]);
            std::size_t len = 1;
            if ((c & 0xE0) == 0xC0)
                len = 2;
            else if ((c & 0xF0) == 0xE0)
                len = 3;
            else if ((c & 0xF8) == 0xF0)
                len = 4;
            if (i + len > text.size())
                len = 1;

            out.append(text, i, len);

            if (c == '\n')
                col = 0;
            else if (len == 3) // a CJK character
            {
                if (++col >= maxChars)
                {
                    out.push_back('\n');
                    col = 0;
                }
            }
            else if (len == 1)
                ++col;

            i += len;
        }
        return out;
    }
}

"""

CALL = ("%(ind)s%(w)s->setCaptionWithReplacing(wrapCJKText(%(arg)s, std::max(10,\n"
        "%(ind)s    (%(w)s->getWidth() - 12) / std::max(8, Settings::gui().mFontSize.get()))));")


def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p, t):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def wrap_call(text, argname):
    pat = re.compile(
        r"^(?P<ind>[ \t]*)(?P<w>\w+)->setCaptionWithReplacing\("
        + re.escape(argname) + r"\);", re.M)
    matches = list(pat.finditer(text))
    if len(matches) != 1:
        raise SystemExit("anchor for %r not unique (%d hits)" % (argname, len(matches)))
    m = matches[0]
    replacement = CALL % {"ind": m.group("ind"), "w": m.group("w"), "arg": argname}
    return text[:m.start()] + replacement + text[m.end():]


def main():
    if not os.path.exists(CPP):
        raise SystemExit("not found: %s (run from the repo root)" % CPP)

    t = read(CPP)
    if "wrapCJKText" in t:
        print("already patched")
        return

    m = re.search(r"^[ \t]*MessageBox::MessageBox\(MessageBoxManager ?&", t, re.M)
    if not m:
        raise SystemExit("MessageBox constructor not found")
    t = t[:m.start()] + HELPER + t[m.start():]

    t = wrap_call(t, "mMessage")
    t = wrap_call(t, "message")

    if "#include <algorithm>" not in t:
        inc = re.search(r'^#include "messagebox\.hpp"[ \t]*$', t, re.M)
        if not inc:
            raise SystemExit("include anchor not found")
        t = t[:inc.end()] + "\n\n#include <algorithm>" + t[inc.end():]

    write(CPP, t)
    print("patched:", CPP)


if __name__ == "__main__":
    main()
