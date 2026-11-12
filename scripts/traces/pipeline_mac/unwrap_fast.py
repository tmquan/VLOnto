"""Linear-time drop-in for vnlegal_text.unwrap_lines with identical output.

The original appends each continuation line to the paragraph string (prev + " " + s) and re-tests the whole
paragraph with _is_caps(prev) and _TERM.search(prev) for every line, which is quadratic in the paragraph length
(a 4.5 M-character tariff table takes 16 s, longer tables minutes). Here the paragraph is kept as a list of parts
with incremental letter counts (for _is_caps), a 1,000-character head (for the anchored _HEAD match) and a
1,000-character tail (for the end-anchored _TERM search, with a full search when the tail is only closing
quotes/spaces). Verified byte-identical on a document sample before use."""
import re
import vnlegal_text as V

_TAILN = 1000
_CLOSERS = re.compile(r"[\s”\"’)]*")


class _Para:
    __slots__ = ("parts", "n_alpha", "n_upper", "head", "tail")

    def __init__(self, s):
        self.parts = [s]
        self.n_alpha = 0
        self.n_upper = 0
        self._count(s)
        self.head = s[:_TAILN]
        self.tail = s[-_TAILN:]

    def _count(self, s):
        for c in s:
            if c.isalpha():
                self.n_alpha += 1
                if c.isupper():
                    self.n_upper += 1

    def add(self, s):
        self.parts.append(s)
        self._count(s)
        if len(self.head) < _TAILN:
            self.head = (self.head + " " + s)[:_TAILN]
        self.tail = (self.tail + " " + s)[-_TAILN:]

    def is_caps(self):
        return self.n_alpha >= 2 and self.n_upper / self.n_alpha > 0.85

    def term(self):
        if V._TERM.search(self.tail):
            return True
        if _CLOSERS.fullmatch(self.tail):
            return bool(V._TERM.search(" ".join(self.parts)))
        return False

    def is_head(self):
        return bool(V._HEAD.match(self.head))

    def text(self):
        return " ".join(self.parts)


def unwrap_lines_fast(text):
    out = []
    cur = None
    for ln in text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if cur is None:
            cur = _Para(s)
            continue
        if V.MARKER.match(s):
            out.append(cur.text()); cur = _Para(s); continue
        first = s[0]
        cont = False
        if first.islower() or first in ",;:.)]}%”’" or (first.isdigit() and not re.match(r"^\d{1,3}[\.\)]\s", s)):
            cont = True
        else:
            head = cur.is_head()
            if cur.is_caps() and V._is_caps(s) and not head:
                cont = True
            elif not cur.term() and not head and not cur.is_caps():
                cont = True
        if cont:
            cur.add(s)
        else:
            out.append(cur.text()); cur = _Para(s)
    if cur is not None:
        out.append(cur.text())
    return "\n".join(out)
