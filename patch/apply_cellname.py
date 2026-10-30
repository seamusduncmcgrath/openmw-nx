#!/usr/bin/env python3
"""Translate cell display names through cellname.txt.

The Chinese Morrowind package ships a table of English -> Chinese cell names
(the "Morrowind.cel" / "cellname.txt" of the PC build). Vanilla Morrowind and
upstream OpenMW never look at it; the Chinese build has a private patch.

This patch makes the display path use it: World::getCellName() is the single
function the map, the loading screens and the travel (boat / silt strider)
lists go through, so translating there renames everything without touching
cell identity, ids or saved games.

The table is read once, lazily, from "cellname.txt" in the working directory
(sdmc:/switch/openmw/cellname.txt on the Switch).
"""
import io
import os
import re

ROOT = os.getcwd()
CPP = os.path.join(ROOT, "apps", "openmw", "mwworld", "worldimp.cpp")

HELPER = r"""
namespace
{
    // English -> Chinese cell names, read once from cellname.txt
    const std::unordered_map<std::string, std::string>& cellNameTable()
    {
        static const std::unordered_map<std::string, std::string> table = []() {
            std::unordered_map<std::string, std::string> result;

            std::ifstream in("cellname.txt");
            if (!in.is_open())
                return result;

            std::string line;
            std::string pending;
            while (std::getline(in, line))
            {
                if (!line.empty() && line.back() == '\r')
                    line.pop_back();
                if (line.empty())
                {
                    pending.clear();
                    continue;
                }
                if (line[0] == '>')
                    pending = line.substr(1);
                else if (line[0] == '=' && !pending.empty())
                {
                    result[pending] = line.substr(1);
                    pending.clear();
                }
            }
            return result;
        }();
        return table;
    }

    std::string translatedCellName(const std::string& name)
    {
        if (name.empty())
            return std::string();

        const std::unordered_map<std::string, std::string>& table = cellNameTable();
        const auto it = table.find(name);
        if (it == table.end())
            return std::string();
        return it->second;
    }
}

"""

INSERT = """        {
            const MWWorld::CellStore* cellStore = %(param)s;
            if (cellStore != nullptr)
            {
                const MWWorld::Cell* worldCell = cellStore->getCell();
                if (worldCell != nullptr)
                {
                    const std::string translated
                        = translatedCellName(std::string(worldCell->getDisplayName()));
                    if (!translated.empty())
                        return translated;
                }
            }
        }
"""


def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p, t):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def main():
    if not os.path.exists(CPP):
        raise SystemExit("not found: %s (run from the repo root)" % CPP)

    t = read(CPP)
    if "translatedCellName" in t:
        print("already patched")
        return

    # helper before the first MWWorld namespace
    m = re.search(r"^namespace MWWorld\s*$", t, re.M)
    if not m:
        raise SystemExit("namespace MWWorld not found")
    t = t[:m.start()] + HELPER + t[m.start():]

    # Find World::getCellName and insert the lookup right after its opening
    # brace. The definition is matched loosely on purpose: the return type may
    # be std::string or a reference, so anything starting with "World::" and
    # calling getCellName( counts.
    matches = list(re.finditer(r"World::getCellName[ \t]*\(", t))
    if not matches:
        raise SystemExit("World::getCellName not found in worldimp.cpp")

    inserted = 0
    skipped = 0
    param = "cell"
    for m in reversed(matches):
        close = t.find(")", m.end())
        if close < 0:
            continue
        params = t[m.end():close]
        # only the overload that takes a CellStore: another overload may take
        # an ESM::Cell and our snippet would not compile there
        if "CellStore" not in params:
            skipped += 1
            continue

        names = re.findall(r"[A-Za-z_]\w*", params)
        param = names[-1] if names else "cell"

        brace = t.find("{", close)
        if brace < 0:
            continue
        t = t[:brace + 1] + "\n" + (INSERT % {"param": param}) + t[brace + 1:]
        inserted += 1

    print("getCellName definitions patched: %d, skipped: %d (param=%s)"
          % (inserted, skipped, param))

    # includes
    for inc in ("<fstream>", "<unordered_map>"):
        if inc not in t:
            anchor = '#include "worldimp.hpp"'
            if anchor not in t:
                raise SystemExit("include anchor not found")
            t = t.replace(anchor, anchor + "\n\n#include " + inc, 1)

    write(CPP, t)
    print("patched:", CPP)


if __name__ == "__main__":
    main()
