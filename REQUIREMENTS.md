# AMAT System Type Identifier Requirements

Current implemented ruleset: `2026.08.28.1`

This document distinguishes implemented requirements from observations and
open requirements. The versioned classifier and its regression tests are the
executable specification; validation history records why rules changed but
does not by itself establish accuracy on unseen systems.

## Purpose

Build a reusable classification engine that can:

1. Parse system numbers and identify meaningful components and phrases.
2. Inspect Agile BOM data for items that indicate a system type.
3. Differentiate normal builds from NSO builds using the system number.
4. Support two workflows from the same core logic:
   - Identify the system type.
   - Match a system to an existing system template for WD creation.

The system-type and template workflows must share the same parsing and BOM
analysis logic so their decisions remain consistent.

## System Number Structure

A system number contains three hyphen-separated segments:

```text
<slot_number>-<product_family>-<chamber>
```

Example:

```text
510284-DX-GPB
```

| Component | Value |
| --- | --- |
| Slot number | `510284` |
| Product family | `DX` |
| Chamber | `GPB` |

Input should be treated as text. In particular, slot numbers must never be
converted to integers because they can contain letters and leading zeroes.

## Slot Number and Build Type

The base slot number is always exactly six alphanumeric characters.

### Normal build

A normal build contains only the six-character base slot number:

```text
<6-character base>-<product_family>-<chamber>
```

Examples:

```text
707927-XP-GP
708395-XA2-GP
708187-XA3-SLD
708245-XA3T-SLD
510284-DX-GPA
C01628-EY4-GPB
```

### NSO build

An NSO build appends a suffix to the six-character base. The suffix contains
exactly one letter followed by one or two digits:

```text
<6-character base><letter><1 or 2 digits>-<product_family>-<chamber>
```

The suffix letter is not limited to `R`. Known examples include `R`, `P`, and
`Z`.

Examples:

```text
415119R02-DG-GPA
429008R02-DG-GPB
429427R04-DG-GPC
500924R02-DX-GPA
123456P01-DF-GPB
123456Z08-XA3-SLD
C01340R1-EY3-GP2D
```

The suffix should be retained as text so leading zeroes are preserved. Until
its formal business meaning is established, its components are named:

- `nso_suffix`, for example `R1` or `R02`
- `nso_marker`, for example `R`
- `nso_sequence`, for example `1` or `02`

### Structural patterns

The patterns below describe the agreed slot structure. The complete parser
must also require exactly three hyphen-separated segments.

```regex
Normal slot: ^[A-Z0-9]{6}$
NSO slot:    ^(?<base>[A-Z0-9]{6})(?<marker>[A-Z])(?<sequence>[0-9]{1,2})$
```

### NSO full-build gate

A structurally valid NSO must be classified as a full build or a non-full-build
NSO before any system-type rules run.

To identify a full build, recursively traverse the NSO's Agile BOM at all
available depths and inspect item descriptions using a case-insensitive
substring search for:

```text
ENCLOSURE
```

Before accepting full-build evidence, search Document-category BOM rows at all
retrieved depths for the bounded word `RETROFIT`. A matching retrofit document
is definitive non-full-build evidence and takes precedence over every
`ENCLOSURE` match, including enclosure components nested in the retrofit BOM.
Return `NSO` for manual review and retain the matching document as evidence.
A Part-category row mentioning retrofit does not trigger this override.

When there is no retrofit document, an `ENCLOSURE` match anywhere in the BOM
is definitive full-build evidence. A full-build NSO is then eligible for the
same system-number and BOM classification rules defined for normal builds.

For an NSO whose chamber is `INOZ` or `INZC`, explicit configured-INOZ position
evidence or an explicit Ozonator assembly description is also definitive
full-build evidence. This permits an INOZ/INZC NSO with a positively identified
configuration to use the corresponding classification rule even when its BOM
does not contain the word `ENCLOSURE`. Without that positive evidence, the
normal NSO gate still applies.

If the NSO is determined not to be a full build, return the review value:

```text
NSO
```

This `NSO` value is a manual-review result rather than one of the canonical
system-type names. It tells the user to inspect the build and select its type
manually.

BOM size is an additional indication:

- Full builds generally have large BOMs.
- A BOM with 100 items or fewer usually indicates a non-full-build NSO.

The size indication is not a decision rule. A complete recursive BOM with no
retrofit document, no qualifying INOZ evidence, and no `ENCLOSURE` match returns
`MANUAL_REVIEW_NSO` regardless of row count.

Recursive traversal must protect against repeated subassemblies and BOM cycles,
retain the matched item and its depth as evidence, and distinguish a complete
no-match traversal from a failed or incomplete lookup. A failed traversal must
not establish that `ENCLOSURE` is absent.

## Invalid and Excluded Inputs

If a system number does not meet the agreed format, the record is excluded:

1. Leave its system-type output blank.
2. Do not perform BOM classification or template matching for it.
3. Continue processing the remaining records.

An internal exclusion reason may be retained for diagnostics, but it must not
cause a system type to be guessed or populated.

Examples of invalid formats include a three-digit NSO sequence and an extra
fourth segment:

```text
500678N123-DX-GPB
511421-DG-GPA-RMA69550
```

One-digit NSO sequences such as `R1`, `R2`, and `Z3` are valid.

## Product Family

The middle segment is the product family. Known examples currently include:

```text
DF
DG
DX
EY1
EY2
EY3
EY4
ES1
PJ
XA2
XA3
XA3T
XG3T
XP
TY
```

Product-family values are distinct exact values. Classification rules may
explicitly group exact values; the SYM3 rule, for example, groups `XA3` and
`XA3T` without treating either value as a prefix or wildcard.

The list above is based on examples and is not yet confirmed as exhaustive.

## Chamber

The final segment is a chamber identifier, not a serial number. Known formats
and values include:

```text
GP
GPA, GPB, GPC, ...
GP1, GP2, ...
GP2A, GP2B, GP2D, ...
ZGPA, ZGPB, ZGPC, ZGPD, ...
ZGP1, ZGP2, ZGP3, ZGP4, ZGP5, ...
GPUVA, GPUVB, GPUVC, ...
GPLL
INOZ
SLD
INZC
```

The chamber length must not be assumed to be three or four characters. The
complete allowed chamber rules or authoritative chamber list still need to be
defined.

## Parsed Record

A successfully parsed NSO record exposes at least:

```python
{
    "full_system_number": "415119R02-DG-GPA",
    "slot_number": "415119R02",
    "base_slot_number": "415119",
    "build_type": "NSO",
    "nso_suffix": "R02",
    "nso_marker": "R",
    "nso_sequence": "02",
    "product_family": "DG",
    "chamber": "GPA",
}
```

For a normal build, the NSO fields are blank/null and `build_type` is
`NORMAL`.

When grouping sibling chambers, derive a chamber-independent key from the
complete slot number and product family. It is not a stored parser field.
Multiple chamber-specific records can share the derived key:

```text
510284-DX-GPA
510284-DX-GPB
510284-DX-GPC
```

## Classification Behavior

The final system type is selected using evidence from:

1. Parsed system-number components or phrases.
2. The presence or absence of specified items in the Agile BOM.
3. Normal versus NSO build type.

The rule sections below define the implemented mappings, BOM scopes,
precedence, and conflict behavior. Every decision retains rule IDs and evidence
so ambiguous, incomplete, and unknown cases can be reviewed instead of guessed.

## Canonical System Names

Every successful `CLASSIFIED` decision must use one of the following canonical
names. Spelling, capitalization, punctuation, and qualifiers must be preserved
exactly unless the source list is deliberately revised:

```text
DSM PRODUCER SE 1 CHAMBER
DSM PRODUCER SE 1 CHAMBER WITH GPLIS
DSM PRODUCER SE 2 CHAMBER
DSM PRODUCER SE 2 CHAMBER WITH GPLIS
DSM PRODUCER SE 3 CHAMBER
DSM PRODUCER SE 3 CHAMBER WITH GPLIS
DSM PRODUCER GT
DSM PRODUCER GT WITH GPLIS
DSM PRODUCER SE UV CHAMBER
DSM HDP CENTURA AP (DA)
DSM APACHE (DX)
DSM APACHE (DX) WITH GPLIS
ETCH NEXTGEN 1 CHAMBER
ETCH NEXTGEN 2 CHAMBER
ETCH NEXTGEN 3 CHAMBER
ETCH NEXTGEN 4 CHAMBER
ETCH SLD BOX
ETCH SYM3 AP (XA)
ETCH LOAD LOCK (GPLL)
ETCH NAPA (XX)
FEP RADIANCE 1 CHAMBER
FEP RADIANCE DPN CHAMBER
ALD 2 TAN
EPI SINGLE CLUSTER
EPI JOPLIN/HENDRIX
EPI JOPLIN/HENDRIX WITH LDM
EPI ERMIAS
SICONI
TXZ
CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD
CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG
CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD
CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG
CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD
CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG
ASSY, OZONATOR WITH CHAMBER A, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER B, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER C, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER A & C, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER B & C, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER A & B, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE
```

There are currently 42 canonical system names. The following rule sections
define how supported inputs map to them.
`NSO` and `NEEDS REVIEW` are workflow sentinels, not canonical system names.
`NEEDS REVIEW` means the input is structurally valid but uses a system form
outside the current rule book and requires human classification.
`VERIFICATION_REQUIRED` is a decision status, not a system type. A decision
with this status retains a proposed canonical system type but is not approved
for downstream use until a user verifies it.

## System-Number-Only Classification Rules

The following system types can be routed from the system number after structural
validation. Normal builds enter these rules directly. NSO builds enter them only
after the NSO full-build gate confirms a full build; a non-full-build NSO
returns the manual-review value `NSO` instead.

In the table, `<classifiable_slot>` means either an accepted six-character
normal slot or an NSO slot already confirmed as a full build,
`<any_family>` means any structurally valid product-family segment, and
`<any_chamber>` means any structurally valid chamber segment.

| Priority | System-number condition | Canonical output |
| --- | --- | --- |
| 1 | `<classifiable_slot>-<any_family>-SLD` | `ETCH SLD BOX` |
| 2 | `<classifiable_slot>-<any_family>-GPLL` | `ETCH LOAD LOCK (GPLL)` |
| 3 | Chamber is exactly `INOZ` or `INZC` | Configured INOZ candidate; continue with scoped level-2 BOM rules |
| 4 | Product family is exactly `DF` and the chamber contains `UV` | `DSM PRODUCER SE UV CHAMBER` |
| 5 | Family is exactly `XA3` or `XA3T`, and chamber is `GPA`, `GPB`, or `GPC` | `ETCH SYM3 AP (XA)` |
| 6 | Product family is exactly `EY1` or `EY2` | `EPI SINGLE CLUSTER` |
| 7 | Product family is exactly `EY3` or `ES1` | JOPLIN/HENDRIX candidate; continue with applicable-main-BOM `LDS` rule |
| 8 | Product family is exactly `EY4` | `EPI ERMIAS` |
| 9 | Product family is exactly `DA` | `DSM HDP CENTURA AP (DA)` |
| 10 | Product family is exactly `XXT` | `ETCH NAPA (XX)` |
| 11 | Product family is exactly `DF` | Producer SE candidate; continue with chamber-count and level-1 BOM rules |
| 12 | Product family is exactly `DG` | Producer GT candidate; continue with level-1 BOM GPLIS rules |
| 13 | Product family is exactly `DX` | Apache candidate; continue with level-1 BOM GPLIS rules |
| 14 | Product family is exactly `TY` | FEP Radiance candidate; continue with level-1 BOM description rules |
| 15 | Product family is exactly `PJ` | Three-way `SICONI` / `TXZ` / `ALD 2 TAN` candidate; further evidence required |

Priority is significant. For example:

```text
708245-XA3T-SLD -> ETCH SLD BOX
707844-XA3-GPA -> ETCH SYM3 AP (XA)
123456-XA3T-GPA -> ETCH SYM3 AP (XA)
```

The generic `DG` and `DX` branches accept only chamber `GP` or a `GP` chamber
with exactly one trailing letter, such as `GPA` through `GPG`. Other chamber
forms do not enter the Producer GT or Apache rules. They return `NEEDS REVIEW`
without querying Agile, retaining the unfamiliar chamber as evidence. For
example, `511374-DG-GPRR` is structurally valid but `GPRR` is outside the rule
book and must not be inferred as Producer GT.

The `SLD`, `GPLL`, and `INOZ` chamber rules take precedence over generic
product-family rules. This ensures, for example, that a `DG-INOZ` system enters
the configured-INOZ branch rather than the Producer GT branch. `XXT` is a
literal, exact product-family value: `XX` is not a variable and product families
merely ending in `T` do not match this rule.

The Producer SE UV rule uses a case-insensitive `UV` substring match against
the chamber segment, not against the slot number. Known examples are:

```text
510170-DF-GPUVB -> DSM PRODUCER SE UV CHAMBER
510170-DF-GPUVC -> DSM PRODUCER SE UV CHAMBER
```

This is a terminal system-number-only rule. It takes precedence over the
generic `DF` Producer SE branch and does not perform the ordinary chamber-count
or GPLIS checks, because no GPLIS variant exists for the canonical UV type.

## Agile BOM Classification Rules

Some system types cannot be determined from the system number alone. Each rule
below defines its retrieval scope explicitly: direct level 1, bounded levels
1-2, an effective EY main BOM, or recursive traversal for the NSO gate. A rule
must not inspect deeper or broader BOM data than its stated scope.

### EY effective-main-BOM resolution

EY-family systems may place their main BOM inside a single parent/holder part.
Use this resolution only for an EY rule that requires BOM evidence; the current
consumer is the `EY3` Joplin/Hendrix LDS rule:

1. Retrieve the system's level-1 BOM.
2. If it contains more than one item, use those level-1 items as the effective
   main BOM.
3. If it contains exactly one item, treat that item as the parent/holder part,
   retrieve its immediate children, and use those system-level-2 items as the
   effective main BOM.
4. Apply the relevant EY description/item matching rules to the effective main
   BOM, regardless of whether it came from system level 1 or system level 2.

This is a controlled one-level fallback, not a general recursive search. The
resolved BOM retains its source level and holder part number as evidence.

If the initial BOM cannot be retrieved, the sole holder item's BOM cannot be
retrieved, or the resolved BOM is incomplete, leave any BOM-dependent output
blank rather than interpreting missing evidence as absence.

### Producer SE classification

A structurally valid classifiable system number whose product family is exactly
`DF` is a Producer SE system. A classifiable build is either normal or a
confirmed full-build NSO. This identifies the Producer SE branch but does not by
itself determine whether the canonical output is the one-, two-, or
three-chamber variant.

The chamber segment narrows the chamber-count classification:

| `DF` chamber form | Producer SE chamber-count result |
| --- | --- |
| Letter-suffixed chamber such as `GPA`, `GPB`, or `GPC` | One chamber |
| Exact chamber `GP`, with no `A`/`B`/`C` suffix | Either two or three chambers; another rule is required |

Therefore, a classifiable `DF` system with a letter-suffixed `GP` chamber is a
Producer SE one-chamber candidate. Its final GPLIS qualifier is selected using
the level-1 BOM rule below.

#### Producer SE `DF-GP` chamber count

For a classifiable Producer SE system whose chamber is exactly `GP`, retrieve its
level-1 Agile BOM and inspect the level-1 BOM item numbers for chamber-specific
system numbers. A matching child system number must have the same complete slot number and
the exact `DF` product family as the parent, with a chamber of `GPA`, `GPB`, or
`GPC`.

Example parent and matching level-1 children:

```text
Parent: 502756-DF-GP

502756-DF-GPA
502756-DF-GPB
502756-DF-GPC
```

Count distinct matching chamber values; duplicate BOM rows must not increase
the chamber count.

| Distinct matching level-1 child chambers | Chamber-count result |
| --- | --- |
| `GPA`, `GPB`, and `GPC` | Three chambers |
| Any two of `GPA`, `GPB`, and `GPC` | Two chambers |
| One of `GPA`, `GPB`, or `GPC` on a full-build NSO only | One chamber |

Examples of valid two-chamber combinations include `GPA` + `GPB`, `GPA` +
`GPC`, or `GPB` + `GPC`.

For normal builds, fewer than two distinct matching children remains
inconsistent with the agreed multi-chamber rule. A full-build NSO may use a
`DF-GP` parent for one chamber; exactly one matching chamber child establishes
that case. Leave the output blank if no matching child is found, or if the
required BOM retrieval fails or is incomplete.

#### Producer SE multi-chamber GPLIS detection

After a classifiable `DF-GP` system has been identified as a valid two- or
three-chamber Producer SE system, determine its GPLIS qualifier with a staged
BOM search:

1. Inspect the descriptions of the parent `DF-GP` system's level-1 BOM items
   for any shared GPLIS indicator.
2. GPLIS indicators are a bounded `GPLS` token with an optional chamber suffix
   (`GPLSA`, `GPLSB`, or `GPLSC`), `F404M`, or a schematic containing the
   bounded liquid count `1-LIQ`, `2-LIQ`, or `3-LIQ`.
3. If the parent level-1 BOM contains no GPLIS match, retrieve the level-1 BOM
   for each matching chamber child found during chamber counting, such as
   `-GPA`, `-GPB`, and `-GPC`.
4. Inspect each chamber child's level-1 item descriptions using the same shared
   GPLIS indicators as a one-chamber Producer SE system.
5. A match in any chamber child means GPLIS is present. Stop searching once a
   positive match is found.
6. GPLIS is absent only when the parent and every applicable chamber-child BOM
   were retrieved successfully and none of their inspected descriptions match.

The same GPLIS evidence rules apply at the parent and chamber-child levels.

Final classification combines the previously determined chamber count with the
GPLIS result:

| Chamber count | GPLIS found | Canonical output |
| --- | --- | --- |
| Two | No | `DSM PRODUCER SE 2 CHAMBER` |
| Two | Yes | `DSM PRODUCER SE 2 CHAMBER WITH GPLIS` |
| Three | No | `DSM PRODUCER SE 3 CHAMBER` |
| Three | Yes | `DSM PRODUCER SE 3 CHAMBER WITH GPLIS` |

If a positive match is found before a later BOM retrieval would be needed, the
system can safely be classified as GPLIS. If no positive match is found but any
required parent or child BOM retrieval fails or is incomplete, leave the output
blank because GPLIS absence has not been established.

#### Producer SE one-chamber GPLIS detection

Inspect the description of every level-1 BOM item using a case-insensitive
search. GPLIS is present if at least one item description contains either of
these strings:

```text
GPLS
F404M
```

GPLIS is also present when a schematic description contains a bounded liquid
count of `1-LIQ`, `2-LIQ`, or `3-LIQ`. Requiring `SCHEMATIC` context prevents
unrelated liquid supply components from qualifying by themselves.

The conditions use OR logic; any indicator is sufficient. `F404M` matching is
not restricted to a complete word or exact description. `GPLS` is token-aware
and may only have the optional chamber suffix `A`, `B`, or `C`.

Known matching examples include:

```text
SYS DF GPLSA
LF-F404M-A-EVD-700,DMDMOS,2 g/min,1/4FV
L-F404M...
SCHEMATIC, 6STK, 1-LIQ, W/VAPORIZER, STD REG, LAVS, PROD GT
```

`GPLSA` matches as the chamber-suffixed GPLS token. Do not match `GPLS` when it
is embedded inside a longer alphanumeric code; plastic tubing description
`TBGPLSTC 1/8OD .03WALL PFA` is not GPLIS evidence. The `F404M` search
intentionally matches variants such as `LF-F404M` and `L-F404M`.

Classification after a successful level-1 BOM retrieval:

| BOM description evidence | Canonical output |
| --- | --- |
| Contains `GPLS`, `F404M`, or a schematic `1-LIQ`/`2-LIQ`/`3-LIQ` indicator | `DSM PRODUCER SE 1 CHAMBER WITH GPLIS` |
| Contains none of the indicators | `DSM PRODUCER SE 1 CHAMBER` |

A missing match and a failed BOM lookup are different outcomes. Only a
successfully retrieved level-1 BOM with none of the GPLIS indicators may be
classified as the non-GPLIS type. If Agile access fails, the BOM is incomplete, or the
description field cannot be read, the classifier must not assume GPLIS is
absent; it must leave the system-type output blank and retain an internal
failure reason.

### Producer GT GPLIS detection

A structurally valid classifiable system number whose product family is exactly
`DG` is a Producer GT system. The canonical outputs do not distinguish Producer
GT by chamber count; they distinguish only whether GPLIS is present:

```text
DSM PRODUCER GT
DSM PRODUCER GT WITH GPLIS
```

Producer GT must reuse the Producer SE GPLIS matching logic:

- For a chamber-specific system such as `DG-GPA`, `DG-GPB`, or `DG-GPC`, inspect
  its level-1 BOM descriptions for `GPLS`, `F404M`, or a schematic containing
  `1-LIQ`, `2-LIQ`, or `3-LIQ`.
- For a parent system whose chamber is exactly `GP`, first inspect its level-1
  BOM descriptions for the shared GPLIS indicators.
- If the parent has no GPLIS match, identify its same-complete-slot, exact-`DG`
  chamber-child system numbers (`GPA`, `GPB`, and/or `GPC`) in the parent
  level-1 BOM. Retrieve each child's level-1 BOM and inspect its descriptions
  for the same GPLIS indicators.
- A positive match at any applicable location selects
  `DSM PRODUCER GT WITH GPLIS`.
- A non-GPLIS result is valid only after every required BOM lookup succeeds and
  no description matches. That selects `DSM PRODUCER GT`.
- If no positive match is found and any required BOM lookup fails or is
  incomplete, leave the output blank.

Producer SE, Producer GT, and Apache use one shared GPLIS detector. Output
selection remains specific to the calling family rule.

### Apache GPLIS detection

A structurally valid classifiable system number whose product family is exactly
`DX` is an Apache system. Its canonical outputs are:

```text
DSM APACHE (DX)
DSM APACHE (DX) WITH GPLIS
```

Apache uses the same hierarchical GPLIS-detection behavior as Producer SE and
Producer GT:

- For a chamber-specific system such as `DX-GPA`, `DX-GPB`, or `DX-GPC`, inspect
  its level-1 BOM descriptions for `GPLS`, `F404M`, or a schematic containing
  `1-LIQ`, `2-LIQ`, or `3-LIQ`.
- For a parent system whose chamber is exactly `GP`, first inspect its level-1
  BOM descriptions for the shared GPLIS indicators.
- If the parent has no GPLIS match, identify its same-complete-slot, exact-`DX`
  chamber-child system numbers (`GPA`, `GPB`, and/or `GPC`) in the parent
  level-1 BOM. Retrieve each child's level-1 BOM and inspect its descriptions
  for the same GPLIS indicators.
- A match at any applicable location selects `DSM APACHE (DX) WITH GPLIS`.
- A complete search with no match selects `DSM APACHE (DX)`.
- If no positive match is found and any required lookup fails or is incomplete,
  leave the output blank.

Apache does not have separate one-, two-, or three-chamber canonical names.
Chamber-child discovery controls BOM traversal only and does not change the
base Apache output name.

The shared GPLIS helper must support `DF`, `DG`, and `DX` as supplied product
families. Output selection remains the responsibility of the calling system
family rule.

### ETCH NEXTGEN chamber-count detection

For product families not handled by an earlier direct or family-specific rule,
inspect BOM descriptions at levels 1-2 for NEXTGEN chamber evidence. A
candidate row must contain at least one contextual marker: `DOC`, `PALLET`,
`GP CORE`, or `NGGP`. Within candidate rows, accept only the bounded,
context-aware chamber patterns documented below. Generic letters elsewhere in
a description are not chamber evidence.

Confirmed four-chamber example:

```text
Item number: 0250-83011
Description: DOC GP FULL BUILD 7/7 A&B-0/4 PAL C&D AP ETCH NG GF 125 FW1.28
Evidence: A&B and C&D
Output: ETCH NEXTGEN 4 CHAMBER
```

The combined designators `A&B` and `C&D` identify chambers A, B, C, and D, so
this example has four distinct chambers.

Confirmed three-chamber example:

```text
Item number: 0250-63413
Description: DOC GP 6/1/1/6 PAL ABC HTD STK 1&6 MLD FRCII-S PROE NG
Evidence: ABC
Output: ETCH NEXTGEN 3 CHAMBER
```

The `ABC` designator identifies chambers A, B, and C, so this example has three
distinct chambers.

Confirmed one-chamber example:

```text
Item number: 0250-78512
Description: DOC, GAS PANEL CONFIG, 7/7 GPA, C-AP, ET
Evidence: GPA only
Output: ETCH NEXTGEN 1 CHAMBER
```

In this notation, the standalone `GPA` designator identifies chamber A. Because
no other chamber designator is present, the example has one chamber. Matching
must use token-aware boundaries so unrelated words containing the same letters
do not create false chamber evidence.

Confirmed alternate four-chamber example:

```text
Item number: 0250-68324
Description: DOC, 6/6-AB 0/4-CD, GAS PANEL CONFIG, C-AP, ETCH NGGP
Evidence: AB and CD
Output: ETCH NEXTGEN 4 CHAMBER
```

In this notation, `AB` identifies chambers A and B, while `CD` identifies
chambers C and D. Ampersands are therefore optional in confirmed multi-chamber
designators: both `A&B` + `C&D` and `AB` + `CD` represent four chambers.
Separating punctuation is allowed, including `PAL AB, 0/4 PAL CD`. When both
pairs occur in one qualifying row, the combined four-chamber interpretation
takes precedence over treating the first `PAL AB` as an independent
two-chamber count.

This example also does not contain the contiguous phrase `DOC GP`; it begins
with `DOC,` and contains the NEXTGEN-related text `ETCH NGGP`. Candidate item
selection must account for these known description variants and must not rely
only on the literal phrases `DOC GP` or `DOC GP FULL BUILD`.

Confirmed compact four-chamber example:

```text
Item number: 0250-81510
Description: DOC GP FULL BUILD, 7/7 PALLET ABCD, FRCII-S 500/500, HTD BCL3 STK1, CENT AP NGGP
Evidence: PALLET ABCD
Output: ETCH NEXTGEN 4 CHAMBER
```

The compact `ABCD` designator expands to chambers A, B, C, and D. Chamber
extraction must be context-aware: text such as `BCL3` is process/equipment text
in this example and must not be interpreted as a chamber-B designator.

Confirmed Batch 1 four-chamber variants also include:

```text
DOC, GAS PANEL CONFIG, 6/6-ABCD, SLD, CE
KIT 6/6 PALLET NO FRC CH A CENTURA AP ETCH NG
KIT 6/6 PALLET NO FRC CH B CENTURA AP ETCH NG
KIT 6/6 PALLET NO FRC CH C CENTURA AP ETCH NG
KIT 6/6 PALLET NO FRC CH D CENTURA AP ET
```

In a qualifying DOC description, the bounded compact token `ABCD` represents
four chambers even when it follows a dash such as `6/6-ABCD`. For qualifying
KIT/PALLET rows, accept both `CH-A` and `CH A` notation and count distinct
chamber letters.

#### ETCH NEXTGEN pallet-kit chamber counting

The level-1 BOM must also be searched for qualifying GP CORE pallet-kit items.
Pallet-kit evidence can use either of two structures:

1. Multiple chamber-specific kit rows whose descriptions contain designators
   such as `CH-A`, `CH-B`, `CH-C`, and `CH-D`. Count distinct chamber
   designators across the qualifying rows; do not count duplicate rows or BOM
   quantities as additional chambers.
2. One consolidated multi-chamber kit whose description states the chamber
   count or contains a compact chamber designator such as `ABCD`.

Confirmed four-chamber pallet-kit example:

```text
0244-05039  CIP: KIT GP CORE 6/6 PALLET CH-A W/O FRCIII-S, W/ ENCLOSURE, CENT-AP ETCH NGGP
0244-05040  CIP: KIT GP CORE 6/6 PALLET CH-B W/O FRCIII-S, W/ ENCLOSURE, CENT-AP ETCH NGGP
0244-05047  CIP: KIT GP CORE 0/4 PALLET CH-C (POS 7-10, 12-STK), CENT-AP ETCH NGGP
0244-05048  CIP: KIT GP CORE 0/4 PALLET CH-D (POS 7-10, 12-STK), CENT-AP ETCH NGGP
```

The distinct designator set is `{A, B, C, D}`, so the result is:

```text
ETCH NEXTGEN 4 CHAMBER
```

Qualifying chamber-specific pallet evidence requires both `KIT` and `PALLET` in
the description. `GP CORE` and `ETCH NGGP` are common corroborating markers but
are not required by the current parser.

Confirmed consolidated four-chamber kit evidence includes:

```text
0244-03162  KIT GP CORE 7/7 PALLET 4-CH SLD CENT AP ETCH NG
0244-03246  SLD KIT GP FULL BUILD, 7/7 PALLET ABCD, FRCII-S 500/500, HTD BCL3 STK1, CENT AP NGGP
```

Either the explicit `4-CH` count or the contextual `PALLET ABCD` designator is
sufficient evidence for four chambers. The BOM is not required to contain four
individual `CH-A` through `CH-D` pallet-kit rows when a consolidated kit is
present. Absence of individual pallet-kit rows is not evidence of a lower
chamber count.

For consolidated kit descriptions, parse an explicit standalone `<N>-CH`
token first. If no explicit count exists, parse a chamber designator only from
a recognized context such as `PALLET ABCD`; do not collect arbitrary letters
from the rest of the description.

Grouped pallet chamber designators are also valid. For example, `PALLET
CH-A/B/C` identifies the distinct chamber set `{A, B, C}` and therefore a
three-chamber NEXTGEN system.

DOC-description evidence and pallet-kit evidence are two ways of deriving the
same chamber count. If explicit candidate rows produce different counts, return
`RULE_CONFLICT` with all conflicting evidence instead of guessing.

A single chamber letter found in an otherwise incomplete set of pallet-kit rows
is not allowed to conflict with repeated explicit compact evidence such as
`ABC`. Explicit DOC/GP CORE/PAL compact designators take precedence over a
single incidental pallet `CH` reference. Use pallet chamber counting as the
primary result when no explicit compact count exists, or as corroboration when
its distinct count agrees with the explicit count.

#### System-number chamber-count indications

Historical system-number mappings suggest that product family may correlate
with an ETCH NEXTGEN chamber count. The following supplied examples are labeled
observations:

| System number | Known canonical output |
| --- | --- |
| `708394-XA2-GP` | `ETCH NEXTGEN 4 CHAMBER` |
| `708396-XA2-GP` | `ETCH NEXTGEN 4 CHAMBER` |
| `709490-XP-GP` | `ETCH NEXTGEN 3 CHAMBER` |
| `709095-XP-GP` | `ETCH NEXTGEN 3 CHAMBER` |
| `709491-XP-GP` | `ETCH NEXTGEN 3 CHAMBER` |
| `Z13732-XA1E-GP` | `ETCH NEXTGEN 1 CHAMBER` |
| `708852-XA1-GP` | `ETCH NEXTGEN 4 CHAMBER` |
| `426137R01-XP-GP` | `ETCH NEXTGEN 3 CHAMBER` |
| `707793-XA2-GP` | `ETCH NEXTGEN 4 CHAMBER` |
| `707354-KA-GP` | `ETCH NEXTGEN 2 CHAMBER` |

Observed correlations in this limited sample are:

```text
XA2  -> 4 chambers (3 examples)
XP   -> 3 chambers (4 examples, including one NSO)
XA1  -> 4 chambers (1 example)
XA1E -> 1 chamber  (1 example)
KA   -> 2 chambers (1 example)
```

These correlations are observations only and are not consumed by ruleset
`2026.08.25.2`. Product family is neither a fallback chamber count nor active
conflict evidence. Promote a correlation into executable behavior only after
more independent examples establish a stable rule and regression tests cover
it.

### FEP Radiance subtype detection

A structurally valid classifiable system number whose product family is exactly
`TY` is an FEP Radiance candidate:

```text
<classifiable_slot>-TY-<any_chamber>
```

Confirmed candidate examples include:

```text
A04157-TY-GPA
A04157-TY-GPB
A04157-TY-GPC
A04027-TY-GPA
A04027-TY-GPB
```

Each of these can independently be either DPN or standard Radiance. Product
family `TY`, chamber suffix, number of sibling chambers, and shared base slot do
not resolve the subtype. Retrieve and classify the level-1 BOM for each complete
chamber-specific system number.

Retrieve its Agile level-1 BOM and inspect every level-1 item description using
case-insensitive substring matching:

| Level-1 item-description evidence | Canonical output |
| --- | --- |
| At least one description contains `DPN` | `FEP RADIANCE DPN CHAMBER` |
| No `DPN` match and at least one description contains `RADIANCE` | `FEP RADIANCE 1 CHAMBER` |

Evaluate `DPN` first because it is the more specific subtype. If both `DPN` and
`RADIANCE` occur anywhere in the successfully retrieved level-1 BOM, select
`FEP RADIANCE DPN CHAMBER`.

If neither substring occurs after a complete, successful level-1 BOM retrieval,
leave the output blank because the candidate subtype was not established. Also
leave the output blank if Agile retrieval fails, the BOM is incomplete, or the
item-description field cannot be inspected.

### PJ system-type candidates

A structurally valid classifiable system number whose product family is exactly
`PJ` can be any one of these canonical system types:

```text
SICONI
TXZ
ALD 2 TAN
```

The shared system-number structure is:

```text
<classifiable_slot>-PJ-<any_chamber>
```

Product family `PJ` identifies only this candidate set; it does not distinguish
the three outputs. Resolve the type by searching Agile BOM item descriptions at
both system level 1 and system level 2:

1. Retrieve every level-1 item for the `PJ` system.
2. Retrieve the immediate children of all applicable level-1 items and inspect
   those level-2 items as well.
3. Do not search below system level 2 for this rule.
4. Match descriptions case-insensitively.

Classification indicators are:

| Description evidence anywhere at level 1 or level 2 | Canonical output |
| --- | --- |
| Contains `TXZ` | `TXZ` |
| Contains `ALD TAN`, `ALD2 TAN`, or `ALD TAN II` | `ALD 2 TAN` |
| Contains none of the TXZ or ALD indicators | `SICONI` |

The ALD indicators are case-insensitive substring phrases. `TaN` is a gas name
and may appear with that capitalization, so forms such as `ALD TaN`, `ALD2
TaN`, and `ALD TaN II` must match the corresponding `TAN` indicators. Normalize
ordinary spacing and case for matching while retaining the original description
as evidence.

`SICONI` is an evidence-by-absence fallback. It may be selected only after a
complete, successful inspection of both required BOM levels establishes that
none of the TXZ or ALD indicators occur. If any required BOM retrieval is
incomplete or fails and no positive subtype has already been established, leave
the output blank instead of defaulting to `SICONI`.

TXZ and ALD indicators are guaranteed to be mutually exclusive in a valid `PJ`
BOM. As a defensive data-integrity check, if both ever appear despite that
contract, leave the output blank and retain both matches for diagnosis rather
than silently selecting an incorrect type.

#### PJ system-number indications

Historical system numbers can provide secondary evidence for a `PJ` type, but
they are not definitive and must not replace the two-level BOM rules.

Supplied labeled observations are:

| System number | Known canonical output |
| --- | --- |
| `601158-PJ-ZGP1` | `ALD 2 TAN` |
| `601158-PJ-ZGP2` | `ALD 2 TAN` |
| `601158-PJ-ZGP3` | `ALD 2 TAN` |
| `B11346-PJ-ZGPC` | `SICONI` |
| `B11346-PJ-ZGPD` | `SICONI` |
| `B11346-PJ-ZGP5` | `SICONI` |
| `B10801-PJ-ZGPC` | `SICONI` |
| `B10801-PJ-ZGPD` | `SICONI` |
| `601150-PJ-ZGP1` | `ALD 2 TAN` |
| `601150-PJ-ZGP2` | `ALD 2 TAN` |
| `601150-PJ-ZGP4` | `ALD 2 TAN` |
| `B08866-PJ-ZGP2` | `TXZ` |
| `B08866-PJ-ZGP3` | `TXZ` |
| `B08866-PJ-ZGP5` | `TXZ` |

Within this sample, each base slot is consistently associated with one type:

```text
601158 -> ALD 2 TAN
601150 -> ALD 2 TAN
B11346 -> SICONI
B10801 -> SICONI
B08866 -> TXZ
```

This is historical lookup evidence, not a general pattern inferred from numeric
or alphabetic slot formats. Chamber values also cannot determine the subtype:
for example, `ZGP2` occurs in both ALD and TXZ observations.

Use a matching historical base slot as a consistency indication after the BOM
classification. If it disagrees with BOM evidence, retain both results and flag
the record for review; do not let the system-number indication override the BOM.

### Configured INOZ chamber-count detection

A structurally valid classifiable system number whose chamber is exactly `INOZ`
or `INZC`
is an Ozonator/INOZ candidate. This chamber-specific routing takes precedence
over generic product-family routing. The scoped level-2 BOM then selects either
an explicit Ozonator assembly type or a configured-INOZ chamber-count type.
The BOM planner must therefore request depth 2 for `INOZ` and `INZC` before
applying the generic DG/DX unsupported-chamber shortcut. Regression system
`509080-DG-INZC` has a level-1 `509080-DG-INOZ` holder and the level-2 evidence
`0241-40895  KIT, POSITION ONE, OZONE RACK, SACVD PRODUCER`; it classifies as
`CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD`.
Confirmed system-number example:

```text
510887-DG-INOZ
```

#### Explicit Ozonator assembly descriptions

Before counting configured-INOZ position items, inspect the INOZ candidate's
scoped BOM rows at application depths 1-2 for an explicit Ozonator assembly
description. This covers both direct rows and the known one-holder nesting
structure. The allowed descriptions correspond to these canonical outputs:

```text
ASSY, OZONATOR WITH CHAMBER A, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER B, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER C, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER A & C, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER B & C, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER A & B, PRODUCER SE
ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE
```

Match case-insensitively with normalized ordinary whitespace, while preserving
the canonical output spelling and punctuation. A recognized explicit assembly
description maps directly to its corresponding canonical name and takes
precedence over the configured-INOZ `POSITION` rules below.

Confirmed example:

```text
System number: 510906-DG-INOZ
Level-2 item: 0011-16255
Description: ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE
Output: ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE
```

If multiple different explicit Ozonator assembly descriptions occur in the
same scoped level-2 BOM, leave the output blank and retain the conflicting
matches for review.

#### Configured INOZ position descriptions

Within the same scoped depth-1/depth-2 BOM data, inspect item descriptions for
these case-insensitive standalone phrases:

```text
POSITION ONE
POSITION TWO
POSITION THREE
```

Count distinct position phrases; duplicate rows do not add chambers. Confirmed
example descriptions include:

```text
KIT, POSITION ONE, OZONE RACK, SACVD PRODUCER
KIT, POSITION TWO, OZONE RACK, SACVD PRODUCER
KIT, BLANK-OFF, NON OZONE CHAMBER, ETERNA OZONE RACK, PMD SACVD PRODUCER
```

The `BLANK-OFF, NON OZONE CHAMBER` item does not count as a chamber because it
does not contain one of the position phrases.

Standard configured-INOZ classification is:

| Distinct level-2 position evidence | Canonical output |
| --- | --- |
| Any one distinct position | `CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD` |
| Any two distinct positions | `CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD` |
| All three distinct positions | `CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD` |

After resolving a valid configured-INOZ chamber count, inspect all item
descriptions in the scoped INOZ BOM data retrieved for classification for the
case-insensitive substring `SAMSUNG`. Any mention of `SAMSUNG` selects the
Samsung variant with the same chamber count:

| Chamber count | `SAMSUNG` absent | `SAMSUNG` present |
| --- | --- | --- |
| One | `CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD` | `CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG` |
| Two | `CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD` | `CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG` |
| Three | `CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD` | `CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG` |

This qualifier applies only to configured-INOZ outputs. If an explicit
`ASSY, OZONATOR...` level-2 description selected an Ozonator assembly output,
do not replace it with a configured-INOZ Samsung type.

Confirmed three-chamber example:

```text
System number: 511837-DG-INOZ
Level-2 evidence: POSITION ONE, POSITION TWO, POSITION THREE
Output: CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD
```

Confirmed one-chamber example:

```text
System number: 511669-DG-INOZ
Level-2 evidence: POSITION ONE
Ignored item: KIT, BLANK-OFF, NON OZONE CHAMBER, ETERNA OZONE RACK, PMD SACVD PRODUCER
Output: CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD
```

The chamber count is the number of distinct `POSITION ONE`, `POSITION TWO`, and
`POSITION THREE` phrases. A single position can therefore identify a
one-chamber system even when the sole phrase is `POSITION TWO`. An empty set
must leave the output blank with diagnostic evidence.

Do not search below application depth 2. If the required bounded BOM retrieval
fails or is incomplete, leave the output blank.

The position rules select configured-INOZ outputs only when no explicit
Ozonator assembly description was found. The `SAMSUNG` description indicator
then selects the appropriate qualifier.

### EPI JOPLIN/HENDRIX LDM detection

A structurally valid classifiable system number whose product family is exactly
`EY3` or `ES1` is an EPI JOPLIN/HENDRIX candidate. For `EY3`, resolve its
applicable main BOM using the EY effective-main-BOM rule. For `ES1`, use the
direct main BOM. Inspect every applicable item description for the acronym
`LDS`.

Match `LDS` case-insensitively as a standalone token in a positive,
non-Document kit description. The description must begin with `KIT` and must
not express absence using `W/O`, `W/OUT`, `WITHOUT`, or `NO` before `LDS`.
Confirmed positive matching description forms include:

```text
KIT, LDS 2, BPC TO MAIN W/OUT REFILL, EPI PRIME
KIT, LDS 1, BPC TO MAIN, RP EPI PRIME GP
KIT, LDS, ECAT NETWORK HUB, RP EPI PRIME GP
KIT, LDS 2 BPC TO MAIN, LINES, EPI PRIME
```

Classification after a complete, successful effective-main-BOM retrieval:

| Effective-main-BOM description evidence | Canonical output |
| --- | --- |
| At least one description contains the standalone token `LDS` | `EPI JOPLIN/HENDRIX WITH LDM` |
| No description contains the standalone token `LDS` | `EPI JOPLIN/HENDRIX` |

The BOM evidence uses the acronym `LDS`, while the canonical output qualifier is
`WITH LDM`; preserve this distinction exactly.

Document schematics and negative descriptions do not establish LDM. Confirmed
false-positive examples that must not match include:

```text
SCHEMATIC, MIX, NO PFD111, AC LDS, RP EPI PRIME GP
SCHEMATIC, GAS PANEL W/OUT MIX/AC/LDS
WELDMENT 1, INTERCONN, MAIN DEP-WITHOUT LDS, RFP EPI GP
```

If Agile retrieval fails, the BOM is incomplete, or item descriptions cannot be
inspected, leave the output blank rather than assuming the non-LDM variant.

## Template Matching

Template map version: `2026.08.27.1`.

The template matcher reuses the parser and classification engine, then selects
the approved WD template mapped to the predicted canonical system type. The
user-supplied `System_Type_WD_Template_Mapping.xlsx` file is the source record
for the following implemented mapping:

| Canonical system type | WD template |
| --- | --- |
| `DSM PRODUCER SE 1 CHAMBER` | `SGP_AMAT_SE_1_CH` |
| `DSM PRODUCER SE 1 CHAMBER WITH GPLIS` | `SGP_AMAT_SE_1_CH_GPLIS` |
| `DSM PRODUCER SE 2 CHAMBER` | `SGP_AMAT_SE_2_CH` |
| `DSM PRODUCER SE 2 CHAMBER WITH GPLIS` | `SGP_AMAT_SE_2_CH_GPLIS` |
| `DSM PRODUCER SE 3 CHAMBER` | `SGP_AMAT_SE_3_CH` |
| `DSM PRODUCER SE 3 CHAMBER WITH GPLIS` | `SGP_AMAT_SE_3_CH_GPLIS` |
| `DSM PRODUCER GT` | `SGP_TEMPLATE_AMAT_GT` |
| `DSM PRODUCER GT WITH GPLIS` | `SGP_TEMPLATE_AMAT_GT_GPLIS` |
| `DSM PRODUCER SE UV CHAMBER` | `SGP_TEMPLATE_AMAT_SE_UV` |
| `DSM HDP CENTURA AP (DA)` | `SGP_TEMPLATE_HDP` |
| `DSM APACHE (DX)` | `SGP_TEMPLATE_AMAT_APACHE` |
| `DSM APACHE (DX) WITH GPLIS` | `SGP_TEMPLATE_AMAT_APACHE_GPLIS` |
| `ETCH NEXTGEN 1 CHAMBER` | `SGP_TEMPLATE_AMAT_NEXTGEN_1` |
| `ETCH NEXTGEN 2 CHAMBER` | `SGP_TEMPLATE_AMAT_NEXTGEN_2` |
| `ETCH NEXTGEN 3 CHAMBER` | `SGP_TEMPLATE_AMAT_NEXTGEN_3` |
| `ETCH NEXTGEN 4 CHAMBER` | `SGP_TEMPLATE_AMAT_NEXTGEN_4` |
| `ETCH SLD BOX` | `SGP_TEMPLATE_AMAT_NEXTGEN_SLD` |
| `ETCH SYM3 AP (XA)` | `SGP_TEMPLATE_AMAT_SYM3` |
| `ETCH LOAD LOCK (GPLL)` | `SGP_TEMPLATE_AMAT_GPLL` |
| `ETCH NAPA (XX)` | `SGP_TEMPLATE_NAPA` |
| `FEP RADIANCE 1 CHAMBER` | `SGP_TEMPLATE_RADIANCE` |
| `FEP RADIANCE DPN CHAMBER` | `SGP_TEMPLATE_DPN` |
| `ALD 2 TAN` | `SGP_TEMPLATE_AMAT_SICONI_OATES` |
| `EPI SINGLE CLUSTER` | `SGP_TEMPLATE_AMAT_EPI` |
| `EPI JOPLIN/HENDRIX` | `SGP_TEMPLATE_AMAT_JOPLIN` |
| `EPI JOPLIN/HENDRIX WITH LDM` | `SGP_TEMPLATE_AMAT_JOPLIN_LDS` |
| `EPI ERMIAS` | `SGP_TEMPLATE_AMAT_ERMIAS` |
| `SICONI` | `SGP_TEMPLATE_AMAT_SICONI_OATES` |
| `TXZ` | `SGP_TEMPLATE_AMAT_TXZ` |
| `CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD` | `SGP_TEMPLATE_AMAT_INZC_1` |
| `CONFIGURED INOZ, 1 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG` | `SGP_TEMPLATE_AMAT_INZC_1` |
| `CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD` | `SGP_TEMPLATE_AMAT_INZC_2` |
| `CONFIGURED INOZ, 2 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG` | `SGP_TEMPLATE_AMAT_INZC_2` |
| `CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD` | `SGP_TEMPLATE_AMAT_INZC_3` |
| `CONFIGURED INOZ, 3 CHAMBER, PRODUCER SE/GT SACVD SAMSUNG` | `SGP_TEMPLATE_AMAT_INZC_3` |
| `ASSY, OZONATOR WITH CHAMBER A, PRODUCER SE` | `SGP_TEMPLATE_AMAT_INZC_1` |
| `ASSY, OZONATOR WITH CHAMBER B, PRODUCER SE` | `SGP_TEMPLATE_AMAT_INZC_1` |
| `ASSY, OZONATOR WITH CHAMBER C, PRODUCER SE` | `SGP_TEMPLATE_AMAT_INZC_1` |
| `ASSY, OZONATOR WITH CHAMBER A & C, PRODUCER SE` | `SGP_TEMPLATE_AMAT_INZC_2` |
| `ASSY, OZONATOR WITH CHAMBER B & C, PRODUCER SE` | `SGP_TEMPLATE_AMAT_INZC_2` |
| `ASSY, OZONATOR WITH CHAMBER A & B, PRODUCER SE` | `SGP_TEMPLATE_AMAT_INZC_2` |
| `ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE` | `SGP_TEMPLATE_AMAT_INZC_3` |

Only `CLASSIFIED` decisions may resolve a template automatically. A
`VERIFICATION_REQUIRED` decision may resolve one only after the calling program
has prompted the user and passes an explicit confirmation. Invalid,
unclassified, NSO manual-review, conflict, retrieval-error, and needs-review
decisions must not produce a WD template.

Shared template values are valid. The map contains 42 canonical system types
and 31 unique WD templates; template names are identifiers and must be matched
exactly, including capitalization and underscores.

## Operational Workbook Application

The Windows desktop application exposes exactly two processing modes. Both
modes reuse the same parser, classifier, Agile connector, ten-worker pool, BOM
cache, and mandatory-verification policy. Operational workflow version:
`2026.08.28.1`.

### Find System Type

The input is an `.xlsx` quote-request workbook. Locate a worksheet containing
the exact normalized headers `System Number` and `System Type` on the same row
within the first 25 rows. Header columns are detected rather than hard-coded;
in the supplied `AMAT System Quote Requests - 20250630.xlsx` example they are
`D6` and `H6`, with data beginning on row 7.

For each nonblank System Number cell below the header, classify the value and
write the approved canonical type to the System Type cell on the same row.
Invalid, unclassified, review, retrieval-error, conflict, rejected-verification,
and other unapproved outcomes must leave the output value blank.

### Find WD Template

The input is an `.xlsx` workbook containing a column of system numbers. Prefer
a `System Number` or `System Numbers` header within the first 25 rows and write
the `WD Template` header and results in the immediately adjacent column. A
headerless column is accepted when it is the unique column containing the most
structurally valid system numbers; write results beside the existing rows and
do not add a header.

If the adjacent headed column is nonblank, its normalized header must be
`WD Template`, `Template`, or `System Template`. If the adjacent column has an
unrelated header, or has populated data without an approved header, reject the
workbook rather than overwrite user data.

Classify every system using the same rules as Find System Type, then resolve the
approved canonical type through template map `2026.08.27.1`. Outcomes that
cannot produce an approved system type must leave the adjacent template value
blank.

### Workbook write safety

- Never modify the selected source workbook. Require a different `.xlsx`
  output path and build the result from a temporary copy in the output folder.
- Use hidden Microsoft Excel COM automation and assign cell `Value2` for output
  cells, the optional WD Template header, and the evidence worksheet described
  below. Do not save through `openpyxl`: the supplied quote workbook uses
  extension-based data validation that `openpyxl` would remove.
- Preserve formulas, formatting, list validation, conditional formatting,
  worksheets, and unrelated values. Atomically replace the requested output
  only after Excel saves the temporary copy successfully.
- Microsoft Excel and `pywin32` are runtime prerequisites. Keep Excel hidden,
  disable events, alerts, and link updates, and always close the workbook and
  Excel process after success or failure.
- If the output already exists, require user confirmation before replacement.
- Keep classification and Agile access on background workers so the UI remains
  responsive. Cancellation stops classification and produces no output.

For each `VERIFICATION_REQUIRED` result, display a blocking Yes/No/Cancel prompt
containing the workbook row, system number, and proposed canonical type. Yes
records approval for that run and writes the type or template. No opens a
correction dialog containing the 42 canonical types and an optional feedback
note. A selected correction writes the corrected type or mapped WD template;
`Leave Unresolved` records rejection and leaves the output blank. Cancel aborts
the entire output operation. Never infer approval from a prior workbook value.

### Match evidence and rule feedback

Every returned workbook must contain an `AMAT Match Evidence` worksheet after
the source worksheets. If an application-owned sheet with that name already
exists, refresh it; if the name belongs to unrelated content, allocate a unique
numbered name rather than overwrite it.

Write one evidence row per populated input system number with these fields:

```text
Source Row
System Number
Mode
Build Type
Classification Status
Proposed System Type
Output System Type
Output WD Template
Matched Rule IDs
Decision Evidence
Warnings
User Verification
User Corrected Type
User Notes
Requirements Action
Ruleset Version
Template Map Version
Workflow Version
```

For ordinary classified rows, `User Verification` is `NOT_REQUIRED`. For a
coverage-limited proposal, record one of:

- `CONFIRMED`: keep the proposed type and set `Requirements Action` to
  `CONFIDENCE_EXAMPLE`.
- `CORRECTED`: use the selected canonical correction and set
  `Requirements Action` to `RULE_CORRECTION`.
- `REJECTED`: leave the operational output blank and set
  `Requirements Action` to `RULE_REVIEW`.
- `PENDING`: a defensive state for an unreviewed proposal; leave the output
  blank and set `Requirements Action` to `USER_VERIFICATION_REQUIRED`.

The evidence worksheet is the requirements-refinement handoff. It must retain
the original deterministic proposal and evidence even when a user correction
changes the operational output. User feedback does not automatically modify
`REQUIREMENTS.md` or classifier code; confirmed and corrected examples must be
reviewed, converted into explicit rules where appropriate, and protected by
regression tests before the ruleset version changes.

## Rule Refinement Workbench

The codebase retains a rule-refinement and evaluation subsystem. Its purpose is
to test the documented rules against thousands of
system numbers with user-supplied correct system types, reveal where the rules
fail, and produce evidence that can be used to refine both the implementation
and this requirements document.

This is initially a supervised rule-evaluation workflow rather than a black-box
machine-learning classifier. Deterministic rules remain the authoritative
classifier because they are explainable and can express Agile BOM hierarchy,
absence conditions, precedence, and manual-review behavior explicitly.

### Labeled input

Each labeled example must provide at least:

```text
system_number
expected_system_type
```

Each structurally valid example is linked to its Agile BOM through the direct
WSDL connector. Retrieved data preserves parent/child relationships, item
number, item description, category, quantity, level/depth, traversal path, and
enough status information to distinguish a complete BOM from a failed or
partial retrieval.

### Evaluation output

For every labeled example, the workbench produces:

```text
system_number
expected_system_type
predicted_system_type
evaluation_status
matched_rule_ids
decision_evidence
build_type
warnings_or_failure_reason
```

The report summary and JSON manifest record the ruleset version for the run.

`evaluation_status` distinguishes:

```text
MATCH
MISMATCH
VERIFICATION_REQUIRED
NEEDS_REVIEW
UNCLASSIFIED
EXCLUDED_INVALID_FORMAT
MANUAL_REVIEW_NSO
BOM_RETRIEVAL_ERROR
RULE_CONFLICT
```

The decision trace must identify the exact system-number components, BOM item
numbers/descriptions, levels, matched phrases, counts, and precedence decisions
that produced the prediction. A result without an explainable trace is not
sufficient for rule refinement.

### Reports

The workbench exports an Excel report with four sheets:

- `Summary`: ruleset version, total records, and status counts.
- `Results`: every record and its decision trace.
- `Mismatches`: records whose classified canonical type differs from the label.
- `Needs Review`: every non-match/non-mismatch outcome, including mandatory
  verification, invalid, unclassified, manual-review, retrieval-error,
  conflict, and needs-review statuses.

It also exports a JSON manifest beside the workbook containing the ruleset
version, UTC generation time, total count, status counts, and every result
record. The workbook and manifest form the reproducible review package.

### Refinement cycle

The intended development loop is:

1. Import labeled system numbers and retrieve required BOM data from Agile.
2. Run the current versioned ruleset.
3. Review mismatches, unclassified records, conflicts, and retrieval failures.
   Explicitly verify every `VERIFICATION_REQUIRED` proposal before using it.
4. Separate incorrect rules from bad/incomplete source data.
5. Add or revise a rule and its regression examples.
6. Re-run the complete evaluation set.
7. Accept a ruleset only when it improves the target cases without regressing
   previously correct cases.

Maintain a reserved validation set that is not used while authoring individual
rules. This prevents rules from being overfitted to the same examples used to
create them.

### Machine-learning role

After enough clean labeled examples exist, an optional ML component may rank or
suggest likely system types for `UNCLASSIFIED` records and surface recurring
part numbers or description phrases correlated with a type. Its suggestions
must remain separate from authoritative rule output until validated and
promoted into an explicit rule with regression tests.

The ML model must not silently rewrite `REQUIREMENTS.md`, modify production
rules, or override deterministic results. Human review remains required for a
suggested rule, especially where absence of BOM evidence or incomplete Agile
data affects the decision.
ML ranking or confidence must not bypass a `VERIFICATION_REQUIRED` decision or
silently promote its proposed type to an approved classification.

### Current implementation

The implemented Windows Python desktop application includes:

- Two explicit modes: Find System Type and Find WD Template.
- Header-aware quote-request input and headed or headerless system-number input.
- Atomic output copies with value-only Microsoft Excel COM updates that preserve
  list validation and other workbook features.
- Per-row mandatory verification prompts for coverage-limited classifications.
- Direct Agile BOM retrieval through the existing Agile WSDL service; users
  must not have to export thousands of BOMs.
- A reusable classification engine independent of the UI.
- Versioned, tested Python rules for direct and hierarchical classification.
- A versioned 42-type to 31-template mapping independent of the UI.
- A synchronized in-memory direct-BOM cache for the current application run.
- Retained labeled-evaluation Excel and JSON report export for rule refinement.
- A fixed pool of 10 evaluation workers, ordered output, duplicate-request
  coalescing, cancellation, and completeness tracking.
- Automatic Agile credential loading from the shared
  `Scripts/script_credentials.json` file using `AGILE_USER` and `AGILE_PASS`.
  The application does not display or copy credential values into source,
  reports, logs, or cache data, and does not prompt for login when the shared
  credential file is valid.

Directly embedding an AI assistant is not required for the first version. The
exported review package provides a safer, reproducible handoff for requirements
and rule refinement without sending the complete BOM dataset to an external
model.

### Agile WSDL connector reference

The existing `Bom Compare v6.py` utility is the behavioral reference for Agile
connectivity. It demonstrates:

- Zeep `Client` and `Transport` with a Requests session using HTTP Basic
  authentication.
- Oracle Agile `RequestTableType` and `LoadTableRequestType` SOAP types.
- Calling `loadTable` for class `Part` and table `BOM`.
- Reading child part numbers from `objectReferentId.objectName`.
- Reading item description, category/template, and quantity from returned row
  XML values.
- Following referenced child part numbers to traverse deeper BOM levels.

The workbench connector preserves these integration semantics and adds the
following classification safeguards:

- Never silently swallow SOAP, parsing, authentication, timeout, or child-BOM
  failures. Return structured completeness and failure information.
- Preserve `parent_part_number`, child part number, depth, description,
  category, local quantity, and traversal path for every row.
- Include Document-category rows because NEXTGEN rules depend on `DOC` items.
- Use bounded concurrency and cancellation without creating an independent
  thread pool at every BOM node.
- Evaluate system numbers through a fixed pool of 10 workers. Preserve input
  order in reports, synchronize the shared direct-BOM cache, and coalesce
  concurrent requests for the same part number so Agile is not queried twice.
- Detect cycles per traversal path and record them rather than recursing
  indefinitely.
- Distinguish a valid part with no child BOM from a BOM request that failed.
- Support a recursive/all-level mode for NSO `ENCLOSURE` detection and bounded
  level-1/level-2 modes for rules that require only those levels.

The current cache stores successful direct-child responses by parent part
number in memory. Bounded and recursive snapshots are assembled from those
direct responses, so a shallow snapshot cannot masquerade as a recursive one.
The cache is cleared when the client is recreated and can be cleared
programmatically. Persistent cross-run caching is not implemented.

## Robustness and Known Limits

Ruleset `2026.08.28.1` is robust for the repeatedly exercised rule paths, but
it is not yet complete for every canonical output or every valid system form.
Its strongest property is fail-closed behavior: invalid formats, unfamiliar
DG/DX chambers, incomplete BOM retrievals, conflicting evidence, and missing
required evidence are surfaced for review rather than guessed.

Large Batch 2 exercised 28 of the 42 canonical outputs. High-volume coverage
exists for Joplin/Hendrix, SYM3 AP, Producer GT, Apache, Producer SE one-chamber,
SLD, Single Cluster, and standard configured INOZ. The following outputs had no
Large Batch 2 predictions:

- `DSM PRODUCER SE 3 CHAMBER` without GPLIS.
- `DSM PRODUCER SE UV CHAMBER` and `DSM HDP CENTURA AP (DA)`.
- `ETCH NEXTGEN 1 CHAMBER` and `ETCH NEXTGEN 2 CHAMBER`.
- All three configured-INOZ Samsung variants.
- Six of the seven explicit Ozonator combinations; only `A & B & C` appeared.

Several observed branches remain thin: each Producer SE two-chamber variant
had one example, Producer SE three-chamber WITH GPLIS had three, Radiance DPN
had three, SICONI had four, NEXTGEN four-chamber had two, and NEXTGEN
three-chamber had five. These counts validate examples, not general coverage.

For operational confidence by canonical type, six of the 42 outputs remain
coverage-limited:

- `DSM PRODUCER SE 2 CHAMBER`.
- `DSM PRODUCER SE 2 CHAMBER WITH GPLIS`.
- `DSM PRODUCER SE 3 CHAMBER`.
- `DSM PRODUCER SE 3 CHAMBER WITH GPLIS`.
- `ETCH NEXTGEN 1 CHAMBER`.
- `ETCH NEXTGEN 2 CHAMBER`.

### Mandatory verification for coverage-limited types

Every program that uses this ruleset must require user verification when the
classifier proposes any of the six coverage-limited types above. The classifier
must:

1. Preserve the proposed canonical value in `predicted_system_type`.
2. Return `evaluation_status = VERIFICATION_REQUIRED`, even when the expected
   label equals the proposal; this outcome must not be counted as `MATCH`.
3. Include rule ID `HUMAN-VERIFY-LOW-CONFIDENCE-TYPE` and explain that user
   verification is mandatory.
4. Present a user-visible prompt or equivalent blocking review task.
5. Prevent the proposal from being consumed by system-template selection, WD
   creation, or another downstream workflow until the user confirms it.

The operational desktop application prompts for every such row. It writes a
confirmed proposal, writes an explicitly selected canonical correction, or
leaves an unresolved rejection blank. The retained evaluation report places
unreviewed records in the `Needs Review` sheet. Operational output workbooks
persist the prompt outcome, correction, notes, original proposal, and evidence
in `AMAT Match Evidence` for later requirements refinement.

The four Producer SE outputs depend on rare `DF-GP` structures and will be
reviewed when new examples occur. NEXTGEN 1- and 2-chamber have too few
confirmed naming variants for full confidence. The rare Samsung INOZ outputs,
other Ozonator combinations, Producer SE UV, and DA remain supported: their
rules are direct system-number mappings or exact documented phrases, so rarity
does not make the rule ambiguous.

The batch files have been used to refine rules and contain repeated sibling
systems and repeated records. Their corrected results are regression evidence,
not an unbiased estimate of performance on unseen systems. A true validation
set must be held out by base system so GPA/GPB/GPC siblings cannot be split
between rule development and validation.

Lexical rules remain inherently sensitive to new Agile wording. NEXTGEN,
explicit Ozonator, Radiance, Samsung, LDS, RETROFIT, and GPLIS matches are safe
only for the documented patterns. New wording should produce review or
unclassified outcomes until it is confirmed and added with regression tests.

## Open Requirements

- Define the deferred bare `-GP` input form mentioned during discovery. It does
  not satisfy the current three-segment parser and remains excluded until its
  missing slot/family semantics are supplied.
- Provide an authoritative product-family and chamber-form list. Parsing is
  intentionally structural, with an additional DG/DX guard for unsupported
  chambers such as `GPRR`.
- For rare `DF-GP` systems, inspect and document alternate chamber-count BOM
  structures as they occur. Do not guess when same-slot `GPA`/`GPB`/`GPC`
  children are absent.
- Decide whether BOM size will ever become definitive NSO evidence. It remains
  diagnostic only; `RETROFIT`, explicit INOZ evidence, and `ENCLOSURE` control
  the current gate.
- Collect independent NEXTGEN 1- and 2-chamber DOC and pallet variants as these
  rare systems occur.
- Collect rare Samsung INOZ, alternate Ozonator combination, Producer SE UV,
  and DA examples opportunistically. Their current direct/exact rules remain
  supported and their rarity is not a release blocker.
- Review the remaining `UNCLASSIFIED` and `RULE_CONFLICT` records from large
  batches before treating the ruleset as complete.
- Establish a base-system-grouped holdout dataset that is never used to author
  or tune rules.
- Supply the approved WD template list, historical system-to-template mappings,
  matching attributes, tie-break rules, and output format.
- Decide whether persistent cross-run BOM caching and evaluation-history
  storage are required. The current cache is in-memory only.

## Validation History

### Batch 1

Ruleset `2026.08.18.2` was evaluated against 45 labeled systems using live
Agile WSDL BOM retrieval. Result:

```text
MATCH: 45
MISMATCH: 0
UNCLASSIFIED: 0
```

Covered expected types:

```text
8  DSM APACHE (DX)
6  DSM PRODUCER GT WITH GPLIS
8  DSM PRODUCER SE 1 CHAMBER WITH GPLIS
7  EPI JOPLIN/HENDRIX
6  EPI SINGLE CLUSTER
1  ETCH NEXTGEN 4 CHAMBER
3  ETCH SLD BOX
6  ETCH SYM3 AP (XA)
```

Batch 1 is now a regression dataset: later rule changes must not break these 45
results. Because its failures were used to refine the JOPLIN and NEXTGEN rules,
it is not an independent holdout set and must not be presented as an unbiased
estimate of performance on unseen systems.

### Batch 2

Ruleset `2026.08.18.2` was evaluated against 292 labeled rows. The initial run
produced:

```text
MATCH: 243
MISMATCH: 22
MANUAL_REVIEW_NSO: 16
EXCLUDED_INVALID_FORMAT: 9
RULE_CONFLICT: 1
UNCLASSIFIED: 1
```

Twenty-four expected values were `SEE NOTES`, not canonical system types. Of
those, 15 correctly entered manual NSO review and 9 correctly failed the strict
system-number format. They are review outcomes rather than ordinary
classification mismatches.

Ruleset `2026.08.19.1` addresses the confirmed Batch 2 gaps:

- `INZC` routes identically to `INOZ`.
- One distinct INOZ position means one chamber even if it is `POSITION TWO`.
- Positive INOZ/Ozonator evidence can establish a full-build INZC NSO without
  an `ENCLOSURE` description.
- Repeated explicit NEXTGEN `ABC` evidence takes precedence over one incidental
  pallet `CH B` reference.

These changes were verified against live Agile BOMs for `511837-DG-INZC`,
`505556R01-DG-INZC`, and `709387-XP-GP`.

Three `511295` GPLIS labels were intentionally incorrect test labels. The
classifier correctly returned the GPLIS type from `SYS DF GPLSA/B/C` and nested
F404M evidence. These are confirmed ground-truth errors, not classifier errors:

```text
511295-DF-GPA/GPB/GPC: incorrect label = DSM PRODUCER SE 1 CHAMBER
                       correct type = DSM PRODUCER SE 1 CHAMBER WITH GPLIS
```

This is a required property of the refinement workbench: a labeled value is not
automatically authoritative when it contradicts strong deterministic evidence.
The mismatch report must retain the matched rule and BOM rows so a human can
correct bad training data without weakening a valid rule.

Three Producer GT GPLIS labels were later confirmed as incorrect during the
large-batch review:

```text
511417-DG-GPA/GPB/GPC: labeled without GPLIS but contains confirmed GPLIS BOM
                       evidence.
```

The classifier's WITH GPLIS result is authoritative; no slot-specific exception
is permitted.

### Batch 3

Ruleset `2026.08.19.1` was evaluated against 381 labeled rows. The submitted
evaluation contained:

```text
MATCH: 362
MISMATCH: 7
MANUAL_REVIEW_NSO: 10
EXCLUDED_INVALID_FORMAT: 1
UNCLASSIFIED: 1
```

Ruleset `2026.08.21.2` addresses confirmed classifier gaps found by live Agile
BOM inspection and user review:

- Grouped NEXTGEN pallet text such as `PALLET CH-A/B/C` contributes all three
  distinct chamber letters. This corrects `426137R01-XP-GP` from one chamber
  to three chambers.
- A full-build NSO `DF-GP` may contain exactly one matching chamber child and
  therefore represent a one-chamber Producer SE system. This classifies
  `415612R03-DF-GP` as `DSM PRODUCER SE 1 CHAMBER WITH GPLIS` from its `GPB`
  child and direct `NSO DF GPLSB` evidence. The exception does not apply to
  normal builds.
- A schematic containing a bounded `1-LIQ`, `2-LIQ`, or `3-LIQ` count is
  GPLIS evidence. This corrects `413470R04-DG-GPA/GPB/GPC`, whose schematic is
  `SCHEMATIC, 6STK, 1-LIQ, W/VAPORIZER, STD REG, LAVS, PROD GT`.
- An NSO suffix may contain one or two sequence digits. This makes
  `C01340R1-EY3-GP2D` structurally valid and sends it through the ordinary NSO
  full-build gate and EY3 classification rules. Live Agile retrieval returned
  a complete 352-row recursive BOM with no `ENCLOSURE` match, so its result is
  `MANUAL_REVIEW_NSO` rather than an invalid-format exclusion.

Three submitted labels were confirmed incorrect; they must not be converted
into slot-specific classifier exceptions:

```text
510743-DG-GPB/GPC: labeled DSM PRODUCER GT, but direct BOM contains F404M
511363P01-DG-INZC: labeled DSM PRODUCER GT, but level 2 contains the exact
                   ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE type
```

The ten non-full-build NSOs remain manual-review results because no
`ENCLOSURE` description was found. BOM size alone remains an indication, not
a classification rule. `511065N02-DF-GP` has no retrieved BOM rows and cannot
safely bypass the NSO full-build gate despite its supplied system-type label.

With the submitted labels unchanged, the expected Batch 3 status counts under
ruleset `2026.08.21.2` are:

```text
MATCH: 367
MISMATCH: 3
MANUAL_REVIEW_NSO: 11
EXCLUDED_INVALID_FORMAT: 0
UNCLASSIFIED: 0
```

### Batch 4

Ruleset `2026.08.21.2` was evaluated against 357 labeled rows. The submitted
evaluation contained:

```text
MATCH: 327
MISMATCH: 7
MANUAL_REVIEW_NSO: 20
EXCLUDED_INVALID_FORMAT: 3
```

Ruleset `2026.08.21.3` adds a confirmed NSO gate rule: a Document-category BOM
row containing the bounded word `RETROFIT` establishes a non-full-build NSO
even when nested enclosure components are also present. This changes
`509195R04-DG-GPA/GPB/GPC` from Producer GT classifications to
`MANUAL_REVIEW_NSO`. Live Agile verification found this level-1 document in
all three complete 731-row BOMs:

```text
0250-67974  RETROFIT PROC, AVENTADOR GP, XW16,UNREG, PROD GT
```

The other four mismatches were confirmed as incorrect submitted labels:

```text
511678-DG-GPC: correct type is DSM PRODUCER GT WITH GPLIS; its schematic has
                1-LIQ evidence
511680N01-DF-GPB: correct type is DSM PRODUCER SE 1 CHAMBER; its direct BOM
                  has no confirmed GPLIS indicator
510743-DG-GPB/GPC: correct type is DSM PRODUCER GT WITH GPLIS
```

The three four-segment `RMA` values remain structurally invalid system numbers
under the agreed three-segment format. With the submitted labels unchanged,
the expected Batch 4 status counts under ruleset `2026.08.21.3` are:

```text
MATCH: 327
MISMATCH: 4
MANUAL_REVIEW_NSO: 23
EXCLUDED_INVALID_FORMAT: 3
```

After correcting the four confirmed label errors, the expected counts are 331
matches, zero mismatches, 23 manual-review NSOs, and three invalid-format
exclusions.

### Batch 5

Ruleset `2026.08.21.3` was evaluated against 288 labeled rows. The submitted
evaluation contained:

```text
MATCH: 267
MISMATCH: 1
MANUAL_REVIEW_NSO: 20
```

The sole mismatch was confirmed as an incorrect submitted label already seen
in Batch 3:

```text
511363P01-DG-INZC
submitted: DSM PRODUCER GT
correct:   ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE
```

The classifier's exact level-2 Ozonator assembly evidence remains authoritative,
so Batch 5 requires no classifier change. After correcting that label, the
expected counts are 268 matches, zero mismatches, and 20 manual-review NSOs.

Batch 5 also broadens validation of the `NSO-RETROFIT-NON-FULL-BUILD` rule. It
correctly returned manual review for retrofit documents across Producer GT,
Producer SE, and Apache families, including retrofit evidence found at both
levels 1 and 2.

### Batch 6

Ruleset `2026.08.21.3` was evaluated against 288 labeled rows. The submitted
evaluation contained:

```text
MATCH: 267
MISMATCH: 1
MANUAL_REVIEW_NSO: 20
```

The sole mismatch was again `511363P01-DG-INZC`, whose submitted Producer GT
label was confirmed incorrect. The classifier correctly selected the exact
level-2 type `ASSY, OZONATOR WITH CHAMBER A & B & C, PRODUCER SE`. No rule
change is required. After correcting the label, the expected counts are 268
matches, zero mismatches, and 20 manual-review NSOs.

### Large Batch 1

Ruleset `2026.08.21.3` was evaluated against 1,051 labeled rows. The submitted
evaluation contained:

```text
MATCH: 934
MISMATCH: 28
MANUAL_REVIEW_NSO: 65
UNCLASSIFIED: 16
EXCLUDED_INVALID_FORMAT: 7
RULE_CONFLICT: 1
```

User review confirmed that 24 mismatch rows were incorrect submitted labels.
The remaining four mismatch rows exposed two classifier defects corrected by
ruleset `2026.08.25.1`:

1. `510866-DX-GPA/GPB/GPC` were incorrectly classified WITH GPLIS because the
   unrestricted `GPLS` substring search matched plastic tubing code
   `TBGPLSTC`. GPLS matching is now token-aware and accepts only `GPLS` or its
   known chamber suffixes `GPLSA`, `GPLSB`, and `GPLSC`. Live Agile verification
   returned complete 633-row BOMs and classified all three as `DSM APACHE
   (DX)`.
2. `708572-XA2-GP` was incorrectly counted as two chambers because `PAL AB,`
   was parsed independently while the comma prevented recognition of the
   accompanying `PAL CD`. The paired `AB` and `CD` evidence now takes
   precedence and yields four chambers. Live Agile verification also found
   explicit chamber C and D kits in the complete 218-row BOM.

With the submitted labels unchanged, the expected revised counts are 938
matches and 24 mismatches, with the other statuses unchanged. After correcting
the 24 confirmed label errors, all 28 original mismatch rows become matches;
the 16 unclassified rows and one rule conflict remain separate unresolved
outcomes for further analysis.

### Large Batch 2

Ruleset `2026.08.25.1` was evaluated against 1,061 labeled rows. The submitted
evaluation contained:

```text
MATCH: 882
MISMATCH: 27
MANUAL_REVIEW_NSO: 134
UNCLASSIFIED: 10
EXCLUDED_INVALID_FORMAT: 8
```

User review confirmed that 26 mismatch rows were incorrect submitted labels.
The remaining mismatch exposed an unsupported system form:

```text
511374-DG-GPRR
submitted type: DSM BENTO WITH GPLIS
```

`GPRR` is not a chamber form in the current rule book, and DSM BENTO is not one
of the 42 canonical system types. Ruleset `2026.08.25.2` therefore returns the
noncanonical sentinel `NEEDS REVIEW` under rule
`SYS-UNRECOGNIZED-GPLIS-CHAMBER` instead of falsely entering the Producer GT
branch. For this normal build, the decision is made from the system number
without an Agile query.

With the submitted labels unchanged, the expected revised counts are 882
matches, 26 mismatches, one needs-review result, 134 manual-review NSOs, 10
unclassified records, and eight invalid-format exclusions. After correcting
the 26 confirmed label errors, the expected match count is 908; the
needs-review, manual-review, unclassified, and invalid outcomes remain.
