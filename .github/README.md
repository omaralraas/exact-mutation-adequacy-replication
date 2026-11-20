# Replication package: Exact Mutation Adequacy for Access-Control Policies Is a Property of Guards, Not of a Language

Mohammad Thabet Hassan, Omar Alraas, Abdulrahman Rezki, Ahmed Alameri, Fahad Sadek, Lobna AbuSerrieh
· Canadian University Dubai · submitted to *The Journal of Systems and Software*

This repository has everything behind the paper's numbers: the tool, the measurement
scripts, the JSON artifacts those scripts wrote, the pre-registered protocols, a container
that pins every external tool, and the Lean 4 development. It is a frozen copy of the
[TrustWeave](https://github.com/MohammadThabetHassan/trustweave) repository at commit
[`a5beb630`](https://github.com/omaralraas/exact-mutation-adequacy-replication/tree/a5beb63033a3722a4051bd68241f25e010b0bace), the commit the paper
cites, with that repository's full history. The only commits after `a5beb630` add this
page, [`REPLICATION.md`](../REPLICATION.md), [`CLAIMS.md`](../CLAIMS.md), `replication/` and
the archive metadata. They change no code, artifact or protocol (see
[Checking the snapshot](../REPLICATION.md#checking-the-snapshot)).

The paths the paper names, such as `docs/EXACT_EVALUATION_PROTOCOL.md` or
`scripts/check_manuscript.py`, are relative to the root of this repository.

## Start here

| To | Do this |
|---|---|
| Find where a number in a table or section comes from | [`CLAIMS.md`](../CLAIMS.md) lists the source artifacts for each place in the paper. [`replication/claims.csv`](../replication/claims.csv) has one row per printed figure |
| Check every pinned figure in the manuscript against the artifacts | `TRUSTWEAVE_PAPER=/path/to/main.tex python scripts/check_manuscript.py` (477 pins) |
| Re-run the checks that need no network, in minutes | `docker build -f reproduce/Dockerfile -t trustweave-reproduce .` then `docker run --rm trustweave-reproduce verify` |
| Re-measure the eight corpora at their recorded commits | `run.sh corpora`, then `run.sh membership` ([`reproduce/README.md`](../reproduce/README.md)) |
| Re-run a single study | the command for each artifact is in [`reproduce/README.md`](../reproduce/README.md#each-artifact-and-the-command-that-writes-it) |
| Check the pre-registrations | `python scripts/check_protocols.py` matches each artifact's recorded protocol hash to a protocol in `docs/` |
| Build the Lean 4 proofs | follow [`proofs/lean/README.md`](../proofs/lean/README.md#building) (`lake build`, in a copy outside the checkout) |

[`REPLICATION.md`](../REPLICATION.md) covers each of these in more detail: the environment,
how long each step takes, and what is known not to reproduce exactly.

## Data availability

**In this repository, under the Apache 2.0 licence:**

- the tool (`src/trustweave/`) and the measurement scripts (`scripts/`)
- every artifact the paper reads its numbers from (`docs/*.json`). Each records the corpus
  commit it read, and each pre-registered one records the SHA-256 of its protocol
- the pre-registered protocols (`docs/*PROTOCOL*.md`)
- the 300 generated policies of the payoff study, in full (`docs/generated-policy-sample-v1.json`)
- the reproduction container, which pins OPA, the Kyverno CLI, Cedar, cvc5 and the Python
  dependencies and checks each binary against its release's SHA-256 (`reproduce/`)
- the Lean 4 development and its pinned Mathlib (`proofs/lean/`)

**Public, but not copied here.** These remain under their owners' licences, so they are
identified exactly and fetched rather than redistributed:

- **The eight policy corpora of the membership table**: Azure Policy, AWS IAM managed policies,
  the XACML conformance suites, the Kyverno library, four Rego libraries, Google's Rego policy
  library, 49 third-party Kyverno policies and Cedar's integration tests. Every whole-corpus
  artifact names its repository and commit, and `scripts/clone_pinned_corpora.py`
  (`run.sh corpora`) clones each one at that commit, about 1 GB in all.
  `scripts/measure_third_party_policies.py` fetches the 49 Kyverno files one by one, each
  pinned by commit.
- **The 1,500-file outside-the-vendor sample** (1,149 repositories). The manifests
  `docs/third-party-sample-*-corpus-v1.json` pin every file by repository, path, commit and
  SHA-256.

**Not included:** the manuscript, which is under review. Without it,
`scripts/check_manuscript.py` reports that it has nothing to check. Reviewers can point it
at their copy of the manuscript source.

## Citing

Please cite the paper. To cite this package, use the DOI of the archived release that the
paper's Data availability statement gives. [`CITATION.cff`](../CITATION.cff) cites the
TrustWeave tool itself.

## Questions

Open an issue on this repository, or contact the corresponding author, Lobna AbuSerrieh,
at the address given in the paper.
