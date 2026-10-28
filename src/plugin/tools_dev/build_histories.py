"""Write the bundled histories, src/plugin/data/<repo>.json, from the specs below.

Each history is a small Python library growing commit by commit: features with their tests, docs,
version bumps and comments, and one commit that slips in a regression. A seeded random source picks
the filler commits, so the same specs always give byte-identical files. After building a history it
runs every commit's tests and refuses to write one whose statuses differ from its spec's.

    uv run python -m plugin.tools_dev.build_histories          # rebuild every history
    uv run python -m plugin.tools_dev.build_histories --check  # rebuild in memory, compare with the files
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contract import Repo, Status
from plugin.history import DATA
from plugin.testrun import test_commit

AUTHORS = ["Ada Park", "Ben Ortiz", "Chen Li", "Dana Kim", "Eli Novak", "Farah Haddad"]
START = datetime(2025, 3, 3, 9, 0, tzinfo=UTC)


@dataclass
class Feature:
    name: str
    code: str  # appended to core.py
    test: str  # appended to the test class, a method indented 4 spaces
    message: str


@dataclass
class Spec:
    repo: Repo
    title: str
    commits: int
    bug_at: int
    bug: tuple[str, str]  # the line in core.py the regression replaces, and its replacement
    bug_message: str
    core: str
    tests: str
    features: list[Feature]
    extra_tests: list[tuple[str, str]]  # (topic, test method)
    topics: list[str]
    broken: tuple[int, int] | None = None  # first and last commit that do not load; the next one fixes it
    breakage: tuple[str, str, str] = ("", "", "")  # text appended to core.py, its fix, the fix's message
    decoy: tuple[int, str, str] | None = None  # a good commit: position, message, comment it adds
    seed: int = 580
    expected: list[Status] = field(init=False)

    def __post_init__(self) -> None:
        first_bad = (
            self.broken[1] + 1 if self.broken and self.broken[0] <= self.bug_at <= self.broken[1] else self.bug_at
        )
        skipped = set(range(self.broken[0], self.broken[1] + 1)) if self.broken else set()
        self.expected = [
            Status.SKIP if position in skipped else Status.BAD if position >= first_bad else Status.GOOD
            for position in range(1, self.commits + 1)
        ]


def test_file(package: str, body: str) -> str:
    return f"import unittest\n\nfrom {package} import core\n\n\nclass CoreTest(unittest.TestCase):\n{body}"


def build(spec: Spec) -> dict:
    rng = random.Random(f"{spec.repo.value}-{spec.seed}")
    package = spec.repo.value
    tree = {
        "README.md": f"# {package}\n\n{spec.title}\n",
        "CHANGELOG.md": "# Changelog\n\n- 0.1.0: first release\n",
        f"{package}/__init__.py": f'"""{spec.title}"""\n\n__version__ = "0.1.0"\n',
        f"{package}/core.py": spec.core,
        "tests/__init__.py": "",
        "tests/test_core.py": test_file(package, spec.tests),
    }
    core, tests = f"{package}/core.py", "tests/test_core.py"
    special = {spec.bug_at}
    if spec.broken:
        special |= {spec.broken[0], spec.broken[1] + 1}
    if spec.decoy:
        special.add(spec.decoy[0])
    free = [position for position in range(2, spec.commits + 1) if position not in special]
    step = len(free) / (len(spec.features) + 1)
    feature_at = {free[round(step * (k + 1))]: feature for k, feature in enumerate(spec.features)}
    rest = [position for position in free if position not in feature_at]
    extra_at = dict(zip(sorted(rng.sample(rest, len(spec.extra_tests))), spec.extra_tests, strict=True))
    patch = 0

    def replace(text: str, old: str, new: str) -> str:
        if text.count(old) != 1:
            raise ValueError(f"{spec.repo.value}: {old!r} is not in core.py exactly once")
        return text.replace(old, new)

    commits = [{"message": "Initial import", "changes": dict(tree)}]
    for position in range(2, spec.commits + 1):
        before = dict(tree)
        if position == spec.bug_at:
            tree[core] = replace(tree[core], *spec.bug)
            message = spec.bug_message
        elif spec.broken and position == spec.broken[0]:
            tree[core] += spec.breakage[0]
            message = "wip: start a helper"
        elif spec.broken and position == spec.broken[1] + 1:
            tree[core] = replace(tree[core], spec.breakage[0], spec.breakage[1])
            message = spec.breakage[2]
        elif spec.decoy and position == spec.decoy[0]:
            tree[core] += f"\n# {spec.decoy[2]}\n"
            message = spec.decoy[1]
        elif position in feature_at:
            feature = feature_at[position]
            tree[core] += "\n\n" + feature.code
            tree[tests] += "\n" + feature.test
            message = feature.message
        elif position in extra_at:
            topic, method = extra_at[position]
            tree[tests] += "\n" + method
            message = f"test: cover {topic}"
        else:
            kind = rng.choice(["changelog", "readme", "version", "comment"])
            topic = rng.choice(spec.topics)
            if kind == "changelog":
                tree["CHANGELOG.md"] += f"- note how {topic} behaves on edge inputs\n"
                message = f"docs: changelog entry for {topic}"
            elif kind == "readme":
                tree["README.md"] += f"\n## {topic}\n\nSee `tests/test_core.py` for {topic} examples.\n"
                message = f"docs: document {topic}"
            elif kind == "version":
                patch += 1
                tree[f"{package}/__init__.py"] = f'"""{spec.title}"""\n\n__version__ = "0.1.{patch}"\n'
                message = f"chore: bump version to 0.1.{patch}"
            else:
                tree[core] += f"\n# {topic}: keep this module free of I/O\n"
                message = f"style: note on {topic}"
        changes = {
            path: tree.get(path) for path in sorted(set(before) | set(tree)) if before.get(path) != tree.get(path)
        }
        commits.append({"message": message, "changes": changes})

    when, parent = START, ""
    history = []
    for commit in commits:
        when += timedelta(hours=rng.randint(1, 30), minutes=rng.randint(0, 59))
        body = json.dumps(
            {"parent": parent, "message": commit["message"], "changes": commit["changes"]}, sort_keys=True
        )
        ident = hashlib.sha1(body.encode()).hexdigest()[:10]
        history.append(
            {
                "id": ident,
                "parent": parent,
                "author": rng.choice(AUTHORS),
                "date": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "message": commit["message"],
                "changes": commit["changes"],
            }
        )
        parent = ident
    return {"repo": spec.repo.value, "commits": history}


def serialize(history: dict) -> str:
    return json.dumps(history, indent=1, sort_keys=True) + "\n"


def check_statuses(spec: Spec, history: dict) -> None:
    with tempfile.TemporaryDirectory() as scratch:
        folder = Path(scratch) / "tree"
        got = [test_commit(history, position, folder)[0] for position in range(1, spec.commits + 1)]
    if got != spec.expected:
        wrong = [p for p, (a, b) in enumerate(zip(got, spec.expected, strict=True), start=1) if a != b]
        raise SystemExit(f"{spec.repo.value}: positions {wrong} do not test as the spec expects")


M = "    def "  # a test method's start, indented in the test class

MONEYFMT = Spec(
    repo=Repo.MONEYFMT,
    title="Money amounts held as integer cents.",
    commits=64,
    bug_at=37,
    bug=("    if 2 * remainder >= abs(denominator):\n", "    if 2 * remainder > abs(denominator):\n"),
    bug_message="perf: avoid a comparison in round_half_up",
    core='''"""Money amounts held as integer cents."""


def round_half_up(numerator, denominator):
    """numerator / denominator to the nearest integer, halves away from zero."""
    negative = (numerator < 0) != (denominator < 0)
    whole, remainder = divmod(abs(numerator), abs(denominator))
    if 2 * remainder >= abs(denominator):
        whole += 1
    return -whole if negative else whole


def format_cents(cents, symbol="$"):
    """1234567 -> '$12,345.67'."""
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}{symbol}{dollars:,}.{rest:02d}"


def parse_amount(text):
    """'-$1,234.5' -> -123450."""
    cleaned = text.strip().replace(",", "")
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("-").lstrip("$")
    dollars, _, cents = cleaned.partition(".")
    value = int(dollars or "0") * 100 + int((cents + "00")[:2])
    return -value if negative else value
''',
    tests=f"""{M}test_round_half_up(self):
        self.assertEqual(core.round_half_up(5, 10), 1)
        self.assertEqual(core.round_half_up(-15, 10), -2)
        self.assertEqual(core.round_half_up(14, 10), 1)

{M}test_format_cents(self):
        self.assertEqual(core.format_cents(1234567), "$12,345.67")
        self.assertEqual(core.format_cents(-5), "-$0.05")

{M}test_parse_amount(self):
        self.assertEqual(core.parse_amount("-$1,234.5"), -123450)
        self.assertEqual(core.parse_amount("$0.07"), 7)
""",
    features=[
        Feature(
            "split_evenly",
            'def split_evenly(cents, parts):\n    """Split cents into parts that differ by at most one cent."""\n'
            "    share, extra = divmod(cents, parts)\n    return [share + (1 if k < extra else 0) for k in range(parts)]\n",
            f"{M}test_split_evenly(self):\n        self.assertEqual(core.split_evenly(100, 3), [34, 33, 33])\n",
            "feat: split_evenly",
        ),
        Feature(
            "percent_of",
            'def percent_of(cents, percent):\n    """percent % of cents, rounded half up."""\n'
            "    return round_half_up(cents * percent, 100)\n",
            f"{M}test_percent_of(self):\n        self.assertEqual(core.percent_of(250, 10), 25)\n",
            "feat: percent_of",
        ),
        Feature(
            "add_tax",
            'def add_tax(cents, basis_points):\n    """cents plus a tax given in basis points (825 = 8.25%)."""\n'
            "    return cents + round_half_up(cents * basis_points, 10000)\n",
            f"{M}test_add_tax(self):\n        self.assertEqual(core.add_tax(1000, 800), 1080)\n",
            "feat: add_tax",
        ),
        Feature(
            "convert",
            'def convert(cents, rate_numerator, rate_denominator):\n    """cents at an exchange rate given as a fraction."""\n'
            "    return round_half_up(cents * rate_numerator, rate_denominator)\n",
            f"{M}test_convert(self):\n        self.assertEqual(core.convert(100, 3, 2), 150)\n",
            "feat: convert between currencies",
        ),
        Feature(
            "format_plain",
            'def format_plain(cents):\n    """1234 -> \'12.34\', no symbol or separators."""\n'
            '    return format_cents(cents, symbol="").replace(",", "")\n',
            f'{M}test_format_plain(self):\n        self.assertEqual(core.format_plain(123456), "1234.56")\n',
            "feat: format_plain",
        ),
    ],
    extra_tests=[
        ("format_cents zero", f'{M}test_format_zero(self):\n        self.assertEqual(core.format_cents(0), "$0.00")\n'),
        (
            "parse_amount whole",
            f'{M}test_parse_whole(self):\n        self.assertEqual(core.parse_amount("12"), 1200)\n',
        ),
        (
            "other symbols",
            f'{M}test_format_euro(self):\n        self.assertEqual(core.format_cents(150, "\u20ac"), "\u20ac1.50")\n',
        ),
        ("exact division", f"{M}test_round_exact(self):\n        self.assertEqual(core.round_half_up(20, 10), 2)\n"),
        ("padding", f'{M}test_parse_spaces(self):\n        self.assertEqual(core.parse_amount("  $3.10 "), 310)\n'),
    ],
    topics=["round_half_up", "format_cents", "parse_amount", "split_evenly", "percent_of", "add_tax", "convert"],
)

DATEPARSE = Spec(
    repo=Repo.DATEPARSE,
    title="Calendar dates as (year, month, day) tuples.",
    commits=64,
    bug_at=2,
    bug=(
        "    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)\n",
        "    return year % 4 == 0 and year % 100 != 0\n",
    ),
    bug_message="refactor: shorten is_leap",
    core='''"""Calendar dates as (year, month, day) tuples."""

DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year, month):
    if month == 2 and is_leap(year):
        return 29
    return DAYS[month - 1]


def parse_iso_date(text):
    """'2024-02-29' -> (2024, 2, 29); ValueError for a date that does not exist."""
    year, month, day = (int(part) for part in text.strip().split("-"))
    if not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"no such date: {text}")
    return year, month, day
''',
    tests=f"""{M}test_is_leap(self):
        self.assertTrue(core.is_leap(2000))
        self.assertFalse(core.is_leap(1900))
        self.assertTrue(core.is_leap(2024))

{M}test_parse_iso_date(self):
        self.assertEqual(core.parse_iso_date("2024-02-29"), (2024, 2, 29))
        with self.assertRaises(ValueError):
            core.parse_iso_date("2023-02-29")
""",
    features=[
        Feature(
            "day_of_year",
            "def day_of_year(year, month, day):\n"
            "    return sum(days_in_month(year, k) for k in range(1, month)) + day\n",
            f"{M}test_day_of_year(self):\n        self.assertEqual(core.day_of_year(2023, 3, 1), 60)\n",
            "feat: day_of_year",
        ),
        Feature(
            "format_iso",
            'def format_iso(year, month, day):\n    return f"{year:04d}-{month:02d}-{day:02d}"\n',
            f'{M}test_format_iso(self):\n        self.assertEqual(core.format_iso(7, 3, 9), "0007-03-09")\n',
            "feat: format_iso",
        ),
        Feature(
            "weekday",
            'def weekday(year, month, day):\n    """0 = Monday ... 6 = Sunday."""\n'
            "    offsets = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]\n    if month < 3:\n        year -= 1\n"
            "    sunday_first = (year + year // 4 - year // 100 + year // 400 + offsets[month - 1] + day) % 7\n"
            "    return (sunday_first + 6) % 7\n",
            f"{M}test_weekday(self):\n        self.assertEqual(core.weekday(2024, 1, 1), 0)\n",
            "feat: weekday",
        ),
        Feature(
            "add_days",
            "def add_days(year, month, day, count):\n    for _ in range(count):\n        day += 1\n"
            "        if day > days_in_month(year, month):\n            day, month = 1, month + 1\n"
            "            if month > 12:\n                month, year = 1, year + 1\n    return year, month, day\n",
            f"{M}test_add_days(self):\n        self.assertEqual(core.add_days(2023, 12, 30, 3), (2024, 1, 2))\n",
            "feat: add_days",
        ),
        Feature(
            "is_weekend",
            "def is_weekend(year, month, day):\n    return weekday(year, month, day) >= 5\n",
            f"{M}test_is_weekend(self):\n        self.assertTrue(core.is_weekend(2024, 1, 6))\n",
            "feat: is_weekend",
        ),
    ],
    extra_tests=[
        ("april", f"{M}test_april(self):\n        self.assertEqual(core.days_in_month(2023, 4), 30)\n"),
        (
            "whitespace",
            f'{M}test_parse_strip(self):\n        self.assertEqual(core.parse_iso_date(" 1999-12-31 "), (1999, 12, 31))\n',
        ),
        (
            "month 13",
            f'{M}test_bad_month(self):\n        with self.assertRaises(ValueError):\n            core.parse_iso_date("2020-13-01")\n',
        ),
        ("century years", f"{M}test_leap_1600(self):\n        self.assertTrue(core.is_leap(1600))\n"),
    ],
    topics=["is_leap", "days_in_month", "parse_iso_date", "day_of_year", "weekday", "add_days"],
)

INIPARSE = Spec(
    repo=Repo.INIPARSE,
    title="Read INI text into {section: {key: value}}.",
    commits=64,
    bug_at=64,
    bug=('        if not line or line[0] in "#;":\n', '        if not line or line.startswith("#"):\n'),
    bug_message="refactor: use startswith for comments",
    core='''"""Read INI text into {section: {key: value}}."""


def unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\\"'":
        return value[1:-1]
    return value


def parse_ini(text):
    sections = {}
    current = None
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1].strip(), {})
        elif "=" in line and current is not None:
            key, _, value = line.partition("=")
            current[key.strip().lower()] = unquote(value.strip())
        else:
            raise ValueError(f"line {number}: {raw!r} is not a section, key or comment")
    return sections
''',
    tests=f"""{M}test_parse_ini(self):
        text = "; settings\\n[server]\\nHost = example.org\\n# port below\\nport = 8080\\n"
        self.assertEqual(core.parse_ini(text), {{"server": {{"host": "example.org", "port": "8080"}}}})

{M}test_unquote(self):
        self.assertEqual(core.parse_ini("[a]\\nname = 'Ada'\\n"), {{"a": {{"name": "Ada"}}}})
""",
    features=[
        Feature(
            "get",
            "def get(sections, section, key, default=None):\n    return sections.get(section, {}).get(key.lower(), default)\n",
            f'{M}test_get(self):\n        self.assertEqual(core.get({{"a": {{"k": "v"}}}}, "a", "K"), "v")\n',
            "feat: get with a default",
        ),
        Feature(
            "get_int",
            "def get_int(sections, section, key, default=0):\n    value = get(sections, section, key)\n"
            "    return default if value is None else int(value)\n",
            f'{M}test_get_int(self):\n        self.assertEqual(core.get_int({{"a": {{"n": "7"}}}}, "a", "n"), 7)\n',
            "feat: get_int",
        ),
        Feature(
            "get_bool",
            "def get_bool(sections, section, key, default=False):\n    value = get(sections, section, key)\n"
            '    return default if value is None else value.lower() in ("1", "true", "yes", "on")\n',
            f'{M}test_get_bool(self):\n        self.assertTrue(core.get_bool({{"a": {{"on": "Yes"}}}}, "a", "on"))\n',
            "feat: get_bool",
        ),
        Feature(
            "to_ini",
            "def to_ini(sections):\n    lines = []\n    for name, values in sections.items():\n"
            '        lines.append(f"[{name}]")\n        lines.extend(f"{key} = {value}" for key, value in values.items())\n'
            '    return "\\n".join(lines) + "\\n"\n',
            f'{M}test_to_ini(self):\n        self.assertEqual(core.to_ini({{"a": {{"k": "v"}}}}), "[a]\\nk = v\\n")\n',
            "feat: to_ini",
        ),
        Feature(
            "section_names",
            "def section_names(text):\n    return list(parse_ini(text))\n",
            f'{M}test_section_names(self):\n        self.assertEqual(core.section_names("[b]\\n[a]\\n"), ["b", "a"])\n',
            "feat: section_names",
        ),
    ],
    extra_tests=[
        ("empty text", f'{M}test_empty(self):\n        self.assertEqual(core.parse_ini(""), {{}})\n'),
        (
            "stray lines",
            f'{M}test_stray_line(self):\n        with self.assertRaises(ValueError):\n            core.parse_ini("[a]\\noops\\n")\n',
        ),
        (
            "key case",
            f'{M}test_key_case(self):\n        self.assertEqual(core.parse_ini("[a]\\nKEY=1\\n"), {{"a": {{"key": "1"}}}})\n',
        ),
        ("double quotes", f'{M}test_double_quotes(self):\n        self.assertEqual(core.unquote(\'"x"\'), "x")\n'),
    ],
    topics=["parse_ini", "unquote", "get", "get_int", "get_bool", "to_ini", "comments"],
)

SLUGIFY = Spec(
    repo=Repo.SLUGIFY,
    title="Turn titles into URL slugs.",
    commits=48,
    bug_at=19,
    bug=(
        "    return SEPARATORS.sub(sep, ascii_text.lower()).strip(sep)\n",
        "    return SEPARATORS.sub(sep, ascii_text.lower())\n",
    ),
    bug_message="perf: one pass less in slugify",
    broken=(18, 19),
    breakage=(
        "\n\ndef truncate(text, limit:\n    return text[:limit]\n",
        "\n\ndef truncate(text, limit):\n    return text[:limit]\n",
        "fix: truncate's signature",
    ),
    core='''"""Turn titles into URL slugs."""

import re
import unicodedata

SEPARATORS = re.compile(r"[^a-z0-9]+")


def slugify(text, sep="-"):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return SEPARATORS.sub(sep, ascii_text.lower()).strip(sep)
''',
    tests=f"""{M}test_slugify(self):
        self.assertEqual(core.slugify("  Hello, World!  "), "hello-world")
        self.assertEqual(core.slugify("Top 10 Tips"), "top-10-tips")
""",
    features=[
        Feature(
            "unique_slug",
            "def unique_slug(text, taken):\n    base = slugify(text)\n    if base not in taken:\n        return base\n"
            '    count = 2\n    while f"{base}-{count}" in taken:\n        count += 1\n    return f"{base}-{count}"\n',
            f'{M}test_unique_slug(self):\n        self.assertEqual(core.unique_slug("A b", {{"a-b", "a-b-2"}}), "a-b-3")\n',
            "feat: unique_slug",
        ),
        Feature(
            "slug_words",
            'def slug_words(slug, sep="-"):\n    return [word for word in slug.split(sep) if word]\n',
            f'{M}test_slug_words(self):\n        self.assertEqual(core.slug_words("a-b-c"), ["a", "b", "c"])\n',
            "feat: slug_words",
        ),
        Feature(
            "is_slug",
            'def is_slug(text, sep="-"):\n    return bool(text) and slugify(text, sep) == text\n',
            f'{M}test_is_slug(self):\n        self.assertTrue(core.is_slug("ok-slug"))\n        self.assertFalse(core.is_slug("Not ok"))\n',
            "feat: is_slug",
        ),
        Feature(
            "short_slug",
            'def short_slug(text, words, sep="-"):\n    return sep.join(slug_words(slugify(text, sep), sep)[:words])\n',
            f'{M}test_short_slug(self):\n        self.assertEqual(core.short_slug("one two three", 2), "one-two")\n',
            "feat: short_slug",
        ),
    ],
    extra_tests=[
        (
            "accents",
            f'{M}test_accents(self):\n        self.assertEqual(core.slugify("Cr\u00e8me Br\u00fbl\u00e9e"), "creme-brulee")\n',
        ),
        (
            "custom separators",
            f'{M}test_underscore(self):\n        self.assertEqual(core.slugify("a b", "_"), "a_b")\n',
        ),
        ("empty titles", f'{M}test_empty(self):\n        self.assertEqual(core.slugify(""), "")\n'),
    ],
    topics=["slugify", "separators", "unicode titles", "unique_slug", "slug_words", "is_slug"],
)

CSVSUM = Spec(
    repo=Repo.CSVSUM,
    title="Sum columns of simple CSV text.",
    commits=33,
    bug_at=17,
    bug=(
        '    return str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))\n',
        '    return str(total.quantize(Decimal("0.01")))\n',
    ),
    bug_message="tidy: drop a redundant quantize argument",
    decoy=(16, "fix rounding in totals", "rounding: totals are rounded half up to cents"),
    core='''"""Sum columns of simple CSV text."""

from decimal import ROUND_HALF_UP, Decimal


def parse_csv_line(line):
    """One CSV line's fields; inside quotes, a doubled quote is one quote."""
    fields, field, quoted, index = [], [], False, 0
    while index < len(line):
        char = line[index]
        if quoted:
            if char == '"' and index + 1 < len(line) and line[index + 1] == '"':
                field.append('"')
                index += 1
            elif char == '"':
                quoted = False
            else:
                field.append(char)
        elif char == '"':
            quoted = True
        elif char == ",":
            fields.append("".join(field))
            field = []
        else:
            field.append(char)
        index += 1
    fields.append("".join(field))
    return fields


def column_total(rows, column):
    """The sum of one column's numbers, as a string with 2 decimals, halves rounded up."""
    total = sum((Decimal(row[column]) for row in rows), Decimal(0))
    return str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
''',
    tests=f"""{M}test_parse_csv_line(self):
        self.assertEqual(core.parse_csv_line('a,"b ""c\\"\\"",d'), ["a", 'b "c"', "d"])

{M}test_column_total(self):
        self.assertEqual(core.column_total([["1.005"], ["2"]], 0), "3.01")
""",
    features=[
        Feature(
            "parse_csv",
            "def parse_csv(text):\n    return [parse_csv_line(line) for line in text.splitlines() if line]\n",
            f'{M}test_parse_csv(self):\n        self.assertEqual(core.parse_csv("a,b\\n1,2\\n"), [["a", "b"], ["1", "2"]])\n',
            "feat: parse_csv",
        ),
        Feature(
            "header_index",
            "def header_index(header, name):\n    return [cell.strip().lower() for cell in header].index(name.lower())\n",
            f'{M}test_header_index(self):\n        self.assertEqual(core.header_index(["Id", " Amount"], "amount"), 1)\n',
            "feat: header_index",
        ),
        Feature(
            "sum_named",
            "def sum_named(text, name):\n    header, *rows = parse_csv(text)\n"
            "    return column_total(rows, header_index(header, name))\n",
            f'{M}test_sum_named(self):\n        self.assertEqual(core.sum_named("id,amt\\n1,2.5\\n2,0.25\\n", "amt"), "2.75")\n',
            "feat: sum a column by name",
        ),
    ],
    extra_tests=[
        (
            "empty fields",
            f'{M}test_empty_fields(self):\n        self.assertEqual(core.parse_csv_line(",,"), ["", "", ""])\n',
        ),
        (
            "negative numbers",
            f'{M}test_negative(self):\n        self.assertEqual(core.column_total([["-1.5"], ["0.25"]], 0), "-1.25")\n',
        ),
        (
            "quoted commas",
            f'{M}test_quoted_comma(self):\n        self.assertEqual(core.parse_csv_line(\'"a,b",c\'), ["a,b", "c"])\n',
        ),
    ],
    topics=["parse_csv_line", "column_total", "quoting", "header_index", "parse_csv"],
)

SPECS = [MONEYFMT, DATEPARSE, INIPARSE, SLUGIFY, CSVSUM]


def main() -> None:
    check = "--check" in sys.argv[1:]
    stale = []
    for spec in SPECS:
        history = build(spec)
        check_statuses(spec, history)
        path = DATA / f"{spec.repo.value}.json"
        text = serialize(history)
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            path.write_text(text)
        print(f"{spec.repo.value}: {spec.commits} commits, statuses as the spec expects")
    if stale:
        raise SystemExit(f"stale histories: {', '.join(stale)}; rebuild them")


if __name__ == "__main__":
    main()
