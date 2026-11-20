"""Map every figure the manuscript pins to the place it is printed and the artifact behind it.

`scripts/check_manuscript.py` holds one anchored pattern per quantitative claim and derives
the value each must carry from `docs/*.json`. This script reuses those pins to answer the
reviewer's question the other way round: for Table 7, or Section 9, which artifacts do its
numbers come from, and which script writes them?

    python replication/claims_map.py --paper /path/to/main.tex

It needs `supplement.tex`, `main.aux` and `supplement.aux` beside `main.tex` (the `.aux`
files give the printed numbers of tables, figures and sections). It writes `CLAIMS.md` and
`replication/claims.csv`. The manuscript itself never enters the repository.

Which artifact a claim depends on is found by perturbation: each artifact in turn has every
number in it changed, the pins are recomputed, and a claim depends on the artifact if its
expected value moves. No claim is attributed by reading the code.
"""

from __future__ import annotations

import argparse
import copy
import csv
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import zlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_checker():
    spec = importlib.util.spec_from_file_location("check_manuscript", ROOT / "scripts" / "check_manuscript.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_manuscript"] = module
    spec.loader.exec_module(module)
    return module


# --- which artifact each claim depends on -------------------------------------------------


def perturb(value, path: str = "", mode: str = "numbers"):
    """`value` changed throughout, in one of three ways.

    `numbers`: every number scaled by a factor that differs from leaf to leaf, so ratios move.
    `records`: every list gains a copy of its first element, so counts of records move.
    `labels`: every string gains a suffix, so counts by category move.
    """
    if isinstance(value, dict):
        return {key: perturb(item, f"{path}/{key}", mode) for key, item in value.items()}
    if isinstance(value, list):
        items = [perturb(item, f"{path}/{index}", mode) for index, item in enumerate(value)]
        return items[:1] + items if mode == "records" else items
    if isinstance(value, bool):
        return value
    salt = zlib.crc32(path.encode())
    if mode == "numbers" and isinstance(value, int):
        return value * (2 + salt % 5) + 1 + salt % 3
    if mode == "numbers" and isinstance(value, float):
        return value * (1.1 + (salt % 7) / 10) + 0.0137
    if mode == "labels" and isinstance(value, str):
        return value + "~"
    return value


MODES = ("numbers", "records", "labels")


def perturb_at(value, pattern: tuple[str, ...], mode: str, path: str = ""):
    """`value` with only the fields `pattern` names perturbed; lists are walked through."""
    if not pattern:
        return perturb(value, path, mode)
    if isinstance(value, list):
        return [perturb_at(item, pattern, mode, f"{path}/{index}") for index, item in enumerate(value)]
    if isinstance(value, dict):
        head, rest = pattern[0], pattern[1:]
        return {key: perturb_at(item, rest, mode, f"{path}/{key}") if key == head else item for key, item in value.items()}
    return value


def children(value, pattern: tuple[str, ...]) -> list[str]:
    """The keys one level below `pattern`, across every element of any list on the way."""
    if isinstance(value, list):
        return sorted({key for item in value for key in children(item, pattern)})
    if not isinstance(value, dict):
        return []
    if not pattern:
        return sorted(value)
    return children(value.get(pattern[0]), pattern[1:])


def dependencies(checker, docs: Path, budget: int = 300) -> tuple[list, dict[int, set[str]]]:
    """Which artifacts each pin depends on.

    Each artifact is perturbed whole, in each of the three modes of `perturb`. Where that
    breaks an invariant the pins rely on (a perturbed index no longer indexes, a lookup by
    name finds nothing), the perturbation is narrowed to one field at a time, recursively.
    A pin depends on an artifact if any perturbation of it moves the value the pin demands.
    """
    baseline = checker.numeric_claims(docs)
    depends: dict[int, set[str]] = defaultdict(set)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch) / "docs"
        shutil.copytree(docs, work)
        for path in sorted(docs.glob("*.json")):
            original = json.loads(path.read_text(encoding="utf-8"))
            target = work / path.name
            for mode in MODES:
                pending: list[tuple[str, ...]] = [()]
                trials = 0
                while pending and trials < budget:
                    pattern = pending.pop()
                    trials += 1
                    target.write_text(json.dumps(perturb_at(copy.deepcopy(original), pattern, mode)), encoding="utf-8")
                    try:
                        moved = checker.numeric_claims(work)
                    except Exception:  # noqa: BLE001 - any failure means "narrow the perturbation"
                        below = children(original, pattern)
                        if below and len(pattern) < 6:
                            pending.extend(pattern + (key,) for key in below)
                        continue
                    if len(moved) != len(baseline):
                        continue
                    for index, (before, after) in enumerate(zip(baseline, moved)):
                        if before[1] != after[1]:
                            depends[index].add(path.stem)
            shutil.copyfile(path, target)
    return baseline, depends


# --- where each claim is printed ----------------------------------------------------------


def aux_numbers(aux: Path) -> dict[str, str]:
    if not aux.is_file():
        return {}
    text = aux.read_text(encoding="utf-8", errors="replace")
    return dict(re.findall(r"\\newlabel\{([^}]*)\}\{\{([^}]*)\}", text))


def braced(text: str, start: int) -> str:
    """The contents of the brace group opening at `start`."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    return text[start + 1 :]


def plain(title: str) -> str:
    title = re.sub(r"\\[a-zA-Z]+\*?(\[[^]]*\])?", "", title)
    return re.sub(r"[{}~]", " ", title).replace("\\", "").strip().replace("  ", " ")


def units(flat: str, numbers: dict[str, str], prefix: str) -> list[tuple[int, int, str]]:
    """(start, end, name) of every abstract, float and section, innermost last."""
    found: list[tuple[int, int, str]] = []
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", flat)
    if abstract:
        found.append((abstract.start(), abstract.end(), "Abstract"))

    counters = [0, 0]
    named: list[tuple[int, str]] = []
    for head in re.finditer(r"\\(section|subsection)(\*?)\{", flat):
        level = 0 if head.group(1) == "section" else 1
        raw = braced(flat, head.end() - 1)
        title = plain(raw)
        label = re.match(r"\s*\\label\{([^}]*)\}", flat[head.end() + len(raw) + 1 :])
        if head.group(2):
            named.append((head.start(), title))
            continue
        counters[level] += 1
        if level == 0:
            counters[1] = 0
        number = f"{prefix}{counters[0]}" + (f".{counters[1]}" if level else "")
        # The .aux is the printed truth; a counted number that disagrees means this parse is wrong.
        if label and label.group(1) in numbers and numbers[label.group(1)] != number:
            raise SystemExit(f"section numbering disagrees with the .aux: {label.group(1)} is {numbers[label.group(1)]}, counted {number}")
        named.append((head.start(), f"Section {number} ({title})"))
    for position, (start, name) in enumerate(named):
        end = named[position + 1][0] if position + 1 < len(named) else len(flat)
        found.append((start, end, name))

    counts = {"table": 0, "figure": 0}
    for begin in re.finditer(r"\\begin\{(table|figure)\*?\}", flat):
        kind = begin.group(1)
        end = flat.find(f"\\end{{{kind}", begin.end())
        span = flat[begin.start() : end]
        counts[kind] += 1
        label = re.search(r"\\label\{([^}]*)\}", span)
        number = numbers.get(label.group(1)) if label else None
        found.append((begin.start(), end, f"{kind.title()} {number or prefix + str(counts[kind])}"))
    return found


def locate(position: int, spans: list[tuple[int, int, str]]) -> str:
    inside = [span for span in spans if span[0] <= position < span[1]]
    if not inside:
        return "Front matter"
    floats = [span for span in inside if span[2].startswith(("Table", "Figure"))]
    if floats:
        return floats[-1][2]
    if any(span[2] == "Abstract" for span in inside):
        return "Abstract"
    return max(inside, key=lambda span: span[0])[2]


# --- how each artifact is reproduced ------------------------------------------------------


def reproduction_rows(readme: Path) -> dict[str, tuple[str, str]]:
    """Artifact -> (tier, command) from the tables in reproduce/README.md."""
    rows: dict[str, tuple[str, str]] = {}
    tier = ""
    for line in readme.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"\*\*(.+?)\.\*\*", line)
        if heading:
            tier = heading.group(1)
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")] if line.startswith("|") else []
        if len(cells) >= 2 and re.fullmatch(r"`[a-z0-9-]+-v\d+`", cells[0]):
            command = cells[1] + (f" — needs {cells[2]}" if len(cells) > 2 and cells[2] else "")
            rows[cells[0].strip("`")] = (tier, command)
    return rows


def writer_scripts(artifact: str) -> list[str]:
    return sorted(
        f"scripts/{path.name}"
        for path in (ROOT / "scripts").glob("*.py")
        if path.name != "check_manuscript.py" and artifact in path.read_text(encoding="utf-8", errors="replace")
    )


def protocols(docs: Path) -> dict[str, str]:
    import hashlib

    by_hash = {
        hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(): path.name
        for path in docs.glob("*PROTOCOL*.md")
    }
    found = {}
    for path in docs.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("protocol_sha256") in by_hash:
            found[path.stem] = by_hash[data["protocol_sha256"]]
    return found


# --- output -------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--docs", type=Path, default=ROOT / "docs")
    parser.add_argument("--out", type=Path, default=ROOT / "CLAIMS.md")
    parser.add_argument("--csv", type=Path, default=ROOT / "replication" / "claims.csv")
    args = parser.parse_args(argv)

    if __debug__:
        # The pins assert invariants between fields (parts sum to a total, and so on); a
        # perturbed copy breaks them by design, so the tracing runs with asserts off. The
        # unperturbed check, with asserts on, is `scripts/check_manuscript.py`.
        import subprocess

        return subprocess.call([sys.executable, "-O", *sys.argv])

    checker = load_checker()
    claims, depends = dependencies(checker, args.docs)

    strip = lambda tex: re.sub(r"\\(ref|pageref|eqref)\{[SM]-", r"\\\1{", tex)
    main_tex = args.paper.read_text(encoding="utf-8")
    supplement_path = args.paper.with_name("supplement.tex")
    documents = [("Main", checker.flatten(strip(main_tex)), aux_numbers(args.paper.with_suffix(".aux")), "")]
    if supplement_path.is_file():
        documents.append(
            ("Supplement", checker.flatten(strip(supplement_path.read_text(encoding="utf-8"))),
             aux_numbers(supplement_path.with_suffix(".aux")), "S")
        )

    rows = []
    for index, (pattern, expected, what) in enumerate(claims):
        for document, flat, numbers, prefix in documents:
            spans = units(flat, numbers, prefix)
            for match in re.finditer(pattern, flat):
                rows.append({
                    "document": document,
                    "location": locate(match.start(), spans),
                    "offset": match.start(),
                    "claim": what,
                    "value": " / ".join(expected),
                    "artifacts": " ".join(sorted(depends.get(index, ()))),
                })
    rows.sort(key=lambda row: (row["document"] != "Main", row["offset"]))

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document", "location", "claim", "value", "artifacts"], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})

    by_place: dict[tuple[str, str], dict] = {}
    for row in rows:
        place = by_place.setdefault((row["document"], row["location"]), {"claims": 0, "artifacts": set()})
        place["claims"] += 1
        place["artifacts"].update(row["artifacts"].split())

    used = sorted({name for row in rows for name in row["artifacts"].split()})
    reproduce = reproduction_rows(ROOT / "reproduce" / "README.md")
    registered = protocols(args.docs)
    resolved = sum(1 for row in rows if row["artifacts"])

    link = lambda name: f"[`{name}`](docs/{name}.json)"
    out = [
        "# Where each number in the paper comes from",
        "",
        "Generated by `replication/claims_map.py` from the pins in `scripts/check_manuscript.py`,",
        "run against the manuscript as submitted. Table, figure and section numbers are those of",
        "the submitted manuscript and its Supporting Information (numbers starting with S).",
        "Every row of [`replication/claims.csv`](replication/claims.csv) is one printed figure,",
        "with the value its artifact gives.",
        "",
        f"- **{len(claims)} pins**, matched at **{len(rows)} places** in the text; "
        f"**{resolved}** of those are traced to the artifact they depend on.",
        "- An artifact counts as a source of a claim when changing the numbers in that artifact",
        "  changes the value the pin demands (see the script's docstring).",
    ]
    if resolved < len(rows):
        out.append(
            f"- The other {len(rows) - resolved} are marked `—`: no perturbation of a single artifact "
            "moved them, typically because they rest on a field that cannot change without "
            "breaking the computation (an identifier, a version string) or on several artifacts at once. "
            "`scripts/check_manuscript.py` still pins each of them."
        )
    out += ["", "## By place in the paper", "", "| Place | Pinned figures | Artifacts |", "|---|---:|---|"]
    for (document, location), place in by_place.items():
        where = location if document == "Main" else f"Supplement: {location}"
        names = ", ".join(link(name) for name in sorted(place["artifacts"])) or "—"
        out.append(f"| {where} | {place['claims']} | {names} |")
    out += [
        "",
        "## By artifact",
        "",
        "How each artifact above is written. *Tier* and *command* are from",
        "[`reproduce/README.md`](reproduce/README.md); *protocol* is the pre-registered protocol whose",
        "SHA-256 the artifact records (`python scripts/check_protocols.py` checks every one).",
        "",
        "| Artifact | Tier | Command, or the script that writes it | Protocol |",
        "|---|---|---|---|",
    ]
    for name in used:
        tier, command = reproduce.get(name, ("", ""))
        membership = re.fullmatch(r"fragment-membership-([a-z]+)-wide-v1", name)
        if not command and membership:
            # reproduce/README.md lists these under `run.sh membership` rather than row by row.
            tier = "Membership"
            command = (
                f"`run.sh membership`, which re-runs `python scripts/fragment_membership.py "
                f"{membership.group(1)} <C>/{name}/... --wide` and diffs the counts"
            )
        if not command:
            command = "read by " + (", ".join(f"`{script}`" for script in writer_scripts(name)) or "—")
        protocol = registered.get(name)
        protocol = f"[`{protocol}`](docs/{protocol})" if protocol else ""
        out.append(f"| {link(name)} | {tier} | {command} | {protocol} |")
    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{len(claims)} pins, {len(rows)} places, {resolved} traced; wrote {args.out} and {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
