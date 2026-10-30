#!/usr/bin/env python3
"""Add GBK / UTF-8 support to OpenMW's toutf8 component (Switch friendly).

Run from the root of an openmw / openmw-nx checkout:

    python3 patch/apply_gbk_patch.py

It edits:
    components/toutf8/toutf8.hpp
    components/toutf8/toutf8.cpp

and is idempotent: running it twice changes nothing.
"""
import io
import os
import sys

ROOT = os.getcwd()
HPP = os.path.join(ROOT, "components", "toutf8", "toutf8.hpp")
CPP = os.path.join(ROOT, "components", "toutf8", "toutf8.cpp")


def read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def replace_once(text, old, new, what):
    if new in text and old not in text:
        return text  # already applied
    if text.count(old) != 1:
        raise SystemExit(
            "anchor not found (or found %d times) while patching %s:\n%s"
            % (text.count(old), what, old[:200])
        )
    return text.replace(old, new, 1)


# --------------------------------------------------------------------------
# helpers injected into the anonymous namespace of toutf8.cpp
# --------------------------------------------------------------------------
HELPERS = r'''
    // ---- GBK support (table based, no iconv / locale needed) ----
    inline void appendUtf8(unsigned int cp, char*& out)
    {
        if (cp < 0x80)
        {
            *out++ = static_cast<char>(cp);
        }
        else if (cp < 0x800)
        {
            *out++ = static_cast<char>(0xC0 | (cp >> 6));
            *out++ = static_cast<char>(0x80 | (cp & 0x3F));
        }
        else
        {
            *out++ = static_cast<char>(0xE0 | (cp >> 12));
            *out++ = static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
            *out++ = static_cast<char>(0x80 | (cp & 0x3F));
        }
    }

    inline unsigned int gbkLookup(unsigned char lead, unsigned char trail)
    {
        if (lead < GBK_LEAD_MIN || lead > GBK_LEAD_MAX)
            return 0;
        if (trail < GBK_TRAIL_MIN || trail > GBK_TRAIL_MAX)
            return 0;
        return gbk_table[(lead - GBK_LEAD_MIN) * GBK_TRAIL_COUNT + (trail - GBK_TRAIL_MIN)];
    }

    std::size_t gbkToUtf8(std::string_view input, std::string& buffer)
    {
        // worst case: one GBK char (2 bytes) -> 3 UTF-8 bytes
        buffer.resize(input.size() / 2 * 3 + 8);
        char* out = &buffer[0];
        for (std::size_t i = 0; i < input.size();)
        {
            const unsigned char ch = static_cast<unsigned char>(input[i]);
            if (ch < 0x80)
            {
                *out++ = static_cast<char>(ch);
                ++i;
                continue;
            }
            if (i + 1 < input.size())
            {
                const unsigned int cp = gbkLookup(ch, static_cast<unsigned char>(input[i + 1]));
                if (cp != 0)
                {
                    appendUtf8(cp, out);
                    i += 2;
                    continue;
                }
            }
            // unknown pair: keep the byte so nothing is lost silently
            *out++ = static_cast<char>(ch);
            ++i;
        }
        return static_cast<std::size_t>(out - &buffer[0]);
    }

    // reverse table, built once on first use
    const unsigned short* gbkReverseTable()
    {
        static unsigned short reverse[0x10000];
        static bool ready = false;
        if (!ready)
        {
            for (int i = 0; i < GBK_TABLE_SIZE; ++i)
            {
                const unsigned int cp = gbk_table[i];
                if (cp != 0 && reverse[cp] == 0)
                {
                    const int lead = GBK_LEAD_MIN + i / GBK_TRAIL_COUNT;
                    const int trail = GBK_TRAIL_MIN + i % GBK_TRAIL_COUNT;
                    reverse[cp] = static_cast<unsigned short>((lead << 8) | trail);
                }
            }
            ready = true;
        }
        return reverse;
    }

    std::size_t utf8ToGbk(std::string_view input, std::string& buffer)
    {
        const unsigned short* reverse = gbkReverseTable();
        buffer.resize(input.size() + 8);
        char* out = &buffer[0];
        for (std::size_t i = 0; i < input.size();)
        {
            const unsigned char ch = static_cast<unsigned char>(input[i]);
            unsigned int cp = 0;
            std::size_t len = 1;
            if (ch < 0x80)
                cp = ch;
            else if ((ch & 0xE0) == 0xC0 && i + 1 < input.size())
            {
                cp = ((ch & 0x1F) << 6) | (static_cast<unsigned char>(input[i + 1]) & 0x3F);
                len = 2;
            }
            else if ((ch & 0xF0) == 0xE0 && i + 2 < input.size())
            {
                cp = ((ch & 0x0F) << 12) | ((static_cast<unsigned char>(input[i + 1]) & 0x3F) << 6)
                     | (static_cast<unsigned char>(input[i + 2]) & 0x3F);
                len = 3;
            }
            else
            {
                *out++ = '?';
                ++i;
                continue;
            }
            if (cp < 0x80)
            {
                *out++ = static_cast<char>(cp);
            }
            else
            {
                const unsigned short code = reverse[cp];
                if (code == 0)
                {
                    *out++ = '?';
                }
                else
                {
                    *out++ = static_cast<char>(code >> 8);
                    *out++ = static_cast<char>(code & 0xFF);
                }
            }
            i += len;
        }
        return static_cast<std::size_t>(out - &buffer[0]);
    }
'''

GBK_BRANCH = r'''    if (mSourceEncoding == ToUTF8::UTF_8)
        return input;
    if (mSourceEncoding == ToUTF8::GBK)
    {
        const std::size_t n = gbkToUtf8(input, buffer);
        return std::string_view(buffer.data(), n);
    }
'''

LEGACY_GBK_BRANCH = r'''    if (mSourceEncoding == ToUTF8::UTF_8)
        return input;
    if (mSourceEncoding == ToUTF8::GBK)
    {
        const std::size_t n = utf8ToGbk(input, buffer);
        return std::string_view(buffer.data(), n);
    }
'''


def patch_hpp(text):
    text = replace_once(
        text,
        "enum FromType\n    {\n",
        "enum FromType\n    {\n        UTF_8,\n        GBK,\n",
        "FromType enum",
    )
    text = replace_once(
        text,
        "const std::span<const signed char> mTranslationArray;",
        "const std::span<const signed char> mTranslationArray;\n        const FromType mSourceEncoding;",
        "StatelessUtf8Encoder member",
    )
    return text


def patch_cpp(text):
    text = replace_once(
        text,
        '#include "toutf8.hpp"\n',
        '#include "toutf8.hpp"\n\n#include "gbk_table.h"\n',
        "include",
    )
    text = replace_once(
        text,
        "    std::string_view::iterator skipAscii(std::string_view input)\n",
        HELPERS + "\n    std::string_view::iterator skipAscii(std::string_view input)\n",
        "helpers",
    )
    text = replace_once(
        text,
        "            case ToUTF8::WINDOWS_1252:\n                return { ToUTF8::windows_1252, std::size(ToUTF8::windows_1252) };",
        "            case ToUTF8::UTF_8:\n            case ToUTF8::GBK:\n                return {};\n"
        "            case ToUTF8::WINDOWS_1252:\n                return { ToUTF8::windows_1252, std::size(ToUTF8::windows_1252) };",
        "getTranslationArray",
    )
    text = replace_once(
        text,
        "    : mTranslationArray(getTranslationArray(sourceEncoding))\n{\n}",
        "    : mTranslationArray(getTranslationArray(sourceEncoding))\n    , mSourceEncoding(sourceEncoding)\n{\n}",
        "constructor",
    )
    # forward: insert right after the empty-input early return of getUtf8
    marker = (
        "std::string_view StatelessUtf8Encoder::getUtf8(\n"
        "    std::string_view input, BufferAllocationPolicy bufferAllocationPolicy, std::string& buffer) const\n{\n"
        "    if (input.empty())\n        return input;\n"
    )
    text = replace_once(text, marker, marker + GBK_BRANCH, "getUtf8")
    # reverse: same for getLegacyEnc
    marker2 = (
        "std::string_view StatelessUtf8Encoder::getLegacyEnc(\n"
        "    std::string_view input, BufferAllocationPolicy bufferAllocationPolicy, std::string& buffer) const\n{\n"
        "    if (input.empty())\n        return input;\n"
    )
    text = replace_once(text, marker2, marker2 + LEGACY_GBK_BRANCH, "getLegacyEnc")
    # encoding names
    text = replace_once(
        text,
        '    else if (encodingName == "win1252")\n        return ToUTF8::WINDOWS_1252;',
        '    else if (encodingName == "win1252")\n        return ToUTF8::WINDOWS_1252;\n'
        '    else if (encodingName == "gbk")\n        return ToUTF8::GBK;\n'
        '    else if (encodingName == "utf8" || encodingName == "utf-8")\n        return ToUTF8::UTF_8;',
        "calculateEncoding",
    )
    text = replace_once(
        text,
        '    else if (encodingName == "win1252")\n        return "Using default (English) font encoding.";',
        '    else if (encodingName == "win1252")\n        return "Using default (English) font encoding.";\n'
        '    else if (encodingName == "gbk")\n        return "Using Chinese (GBK) font encoding.";\n'
        '    else if (encodingName == "utf8" || encodingName == "utf-8")\n        return "Using Unicode font encoding.";',
        "encodingUsingMessage",
    )
    return text


def main():
    for path in (HPP, CPP):
        if not os.path.exists(path):
            raise SystemExit("not found: %s (run this from the repo root)" % path)

    hpp = patch_hpp(read(HPP))
    cpp = patch_cpp(read(CPP))
    write(HPP, hpp)
    write(CPP, cpp)
    print("patched:", HPP)
    print("patched:", CPP)


if __name__ == "__main__":
    main()
