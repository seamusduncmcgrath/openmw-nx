#!/usr/bin/env python3
"""Temporary topic debugging for the Switch port.

Adds log lines to DialogueManager so we can see, at runtime:

  - which topics the player knows
  - which topics the actor has responses for
  - what addTopicsFromText() parsed out of a response

Run from the repo root, then build the NRO and check openmw.log for
lines starting with "[TOPICDBG]".
"""
import io
import os
import sys

ROOT = os.getcwd()
CPP = os.path.join(ROOT, "apps", "openmw", "mwdialogue", "dialoguemanagerimp.cpp")


def read(p):
    with io.open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(p, t):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def replace_once(text, old, new, what):
    if new in text and old not in text:
        return text
    if text.count(old) != 1:
        raise SystemExit("anchor not found (%d matches) for %s:\n%s"
                         % (text.count(old), what, old[:160]))
    return text.replace(old, new, 1)


def main():
    if not os.path.exists(CPP):
        raise SystemExit("not found: %s" % CPP)

    t = read(CPP)

    # 1) log what the actor has and what the player knows, in getAvailableTopics
    t = replace_once(
        t,
        "        // sort again, because the previous sort was case-sensitive\n"
        "        keywordList.sort(Misc::StringUtils::ciLess);\n"
        "        return keywordList;",
        "        // --- [TOPICDBG] ---\n"
        "        Log(Debug::Info) << \"[TOPICDBG] actorTopics=\" << mActorKnownTopics.size()\n"
        "                         << \" known=\" << mKnownTopics.size()\n"
        "                         << \" listed=\" << keywordList.size();\n"
        "        for (const auto& [id, info] : mActorKnownTopics)\n"
        "            Log(Debug::Info) << \"[TOPICDBG]   actor: \" << id.getRefIdString()\n"
        "                             << (mKnownTopics.count(id) ? \" [known]\" : \" [no]\");\n"
        "\n"
        "        keywordList.sort(Misc::StringUtils::ciLess);\n"
        "        return keywordList;",
        "getAvailableTopics",
    )

    # 2) log what is parsed out of a response text
    t = replace_once(
        t,
        "    void DialogueManager::addTopicsFromText(const std::string& text)\n"
        "    {\n"
        "        updateActorKnownTopics();",
        "    void DialogueManager::addTopicsFromText(const std::string& text)\n"
        "    {\n"
        "        updateActorKnownTopics();\n"
        "        Log(Debug::Info) << \"[TOPICDBG] text: \" << text;",
        "addTopicsFromText head",
    )

    t = replace_once(
        t,
        "        for (const auto& topicId : parseTopicIdsFromText(text))\n"
        "        {\n"
        "            if (mActorKnownTopics.count(topicId))\n"
        "                mKnownTopics.insert(topicId);\n"
        "        }",
        "        for (const auto& topicId : parseTopicIdsFromText(text))\n"
        "        {\n"
        "            Log(Debug::Info) << \"[TOPICDBG] parsed: \" << topicId.getRefIdString()\n"
        "                             << (mActorKnownTopics.count(topicId) ? \" [actor has]\" : \" [actor lacks]\");\n"
        "            if (mActorKnownTopics.count(topicId))\n"
        "                mKnownTopics.insert(topicId);\n"
        "        }",
        "addTopicsFromText loop",
    )

    write(CPP, t)
    print("patched:", CPP)


if __name__ == "__main__":
    main()
