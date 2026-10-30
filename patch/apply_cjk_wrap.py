#!/usr/bin/env python3
"""Wrap Chinese text inside OpenMW's book / dialogue pages.

bookpage.cpp splits text into "words" separated by breaking spaces and only
breaks a line between words. Chinese has no spaces, so a paragraph is a single
giant word that runs off the page.

Two earlier attempts were wrong and produced double line spacing:

  * flushing the pending text after every character (each flush looks like a
    paragraph break), and
  * splitting the word inside add_partial_text().

The book's own hard breaks (a <BR> in the text, which the parser turns into
Typesetter::lineBreak) render with correct spacing, so this patch uses the same
path: after a CJK character the accumulated line is measured, and when the next
character would not fit, lineBreak() starts a new line exactly like <BR> does.
"""
import io
import os

ROOT = os.getcwd()
CPP = os.path.join(ROOT, "apps", "openmw", "mwgui", "bookpage.cpp")

HELPER = r"""
    // CJK: characters that may start/end a line anywhere
    bool ucsCJK(Utf8Stream::UnicodeChar codePoint)
    {
        return (codePoint >= 0x2E80 && codePoint <= 0x2FFF)    // radicals
            || (codePoint >= 0x3000 && codePoint <= 0x303F)    // CJK punctuation
            || (codePoint >= 0x3040 && codePoint <= 0x30FF)    // kana
            || (codePoint >= 0x3400 && codePoint <= 0x4DBF)    // ext A
            || (codePoint >= 0x4E00 && codePoint <= 0x9FFF)    // unified ideographs
            || (codePoint >= 0xF900 && codePoint <= 0xFAFF)    // compatibility
            || (codePoint >= 0xFF00 && codePoint <= 0xFFEF);   // fullwidth forms
    }
"""

OLD_WORD_LOOP = """                while (!stream.eof() && !ucsLineBreak(stream.peek()) && !ucsBreakingSpace(stream.peek()))
                {
                    std::optional<MyGUI::GlyphInfo> info = getGlyphInfo(style->mFont, stream.peek());
                    if (info)
                        wordWidth += static_cast<int>(info->advance + info->bearingX);
                    stream.consume();
                }

                Utf8Stream::Point extent = stream.current();

                if (lead == extent)
                    break;

                if (lead != origin)
                    mPartialWhitespace.emplace_back(style, lead, origin, spaceWidth);
                if (origin != extent)
                    mPartialWord.emplace_back(style, origin, extent, wordWidth);"""

NEW_WORD_LOOP = """                Utf8Stream::UnicodeChar lastChar = 0;

                while (!stream.eof() && !ucsLineBreak(stream.peek()) && !ucsBreakingSpace(stream.peek()))
                {
                    lastChar = stream.peek();
                    std::optional<MyGUI::GlyphInfo> info = getGlyphInfo(style->mFont, lastChar);
                    if (info)
                        wordWidth += static_cast<int>(info->advance + info->bearingX);
                    stream.consume();

                    // a CJK character ends the current word: the line may break
                    // after it, the same way a <BR> in the text does
                    if (ucsCJK(lastChar))
                        break;
                }

                Utf8Stream::Point extent = stream.current();

                if (lead == extent)
                    break;

                if (lead != origin)
                    mPartialWhitespace.emplace_back(style, lead, origin, spaceWidth);
                if (origin != extent)
                    mPartialWord.emplace_back(style, origin, extent, wordWidth);

                if (ucsCJK(lastChar))
                {
                    add_partial_text();
                    const int charWidth = Settings::gui().mFontSize;
                    if (mLine != nullptr && mLine->mRect.right + charWidth > mPageWidth)
                        lineBreak(0.f);
                }"""


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
    if "ucsCJK" in t:
        print("already patched")
        return

    anchor = """            case 0x3000: // IDEOGRAPHIC SPACE
                return true;
            default:
                return false;
        }
    }
}"""
    if t.count(anchor) != 1:
        raise SystemExit("ucsBreakingSpace anchor not found (%d)" % t.count(anchor))
    t = t.replace(anchor, anchor[:-2] + HELPER + "}", 1)

    if t.count(OLD_WORD_LOOP) != 1:
        raise SystemExit("word loop anchor not found (%d)" % t.count(OLD_WORD_LOOP))
    t = t.replace(OLD_WORD_LOOP, NEW_WORD_LOOP, 1)

    write(CPP, t)
    print("patched:", CPP)


if __name__ == "__main__":
    main()
