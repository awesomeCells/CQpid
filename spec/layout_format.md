# CQpid layout format (v1)

The layout file is a plain CSV that says what is in each well. One per experiment (or per plate). It is written by the CQpid app and can also be written by hand in Excel.

General rules:

- UTF-8, comma-separated, one header row. A byte-order mark (Excel's "CSV UTF-8") is fine.
- Column names are case-sensitive and lowercase.
- Empty cells are empty, not `NA`.
- Extra columns are allowed and kept.

---

# Layout file

## Version marker

The first line may be a comment that identifies the format:

```
#cqpid layout v1
```

It is optional. A file without it is read as v1. Files written by the app always include it.

## Columns

| Column | Required | Content |
|---|---|---|
| `plate` | yes | Plate identifier, e.g. `1`, `TR1`, `plate_0h`. Links the layout to a Cq export. |
| `well` | yes | Well ID: row letter + column number. `A1` and `A01` are both accepted (the app writes `A01`). 96- and 384-well plates (rows A–P, columns 1–24). |
| `role` | yes | `sample`, `noRT`, `NTC`, `IPC`, `std` or `empty` (see below). |
| `sample` | depends on role | Sample ID, e.g. `S1`. One ID per cDNA tube / biological sample. |
| `target` | yes, unless `empty` | Target (primer pair) name. |
| `dilution` | for `std` wells | Fold dilution of the template in a `std` well: `1` (undiluted), `10`, `100`, … A number ≥ 1. Empty for other roles. The column can be left out when there are no `std` wells. |
| `primer` | no | Label of the primer pair used for the target, e.g. `P1/2`. Same value in every well of a target. Written by the app when set; not a sample variable. |
| `reference` | no | `TRUE` for reference (housekeeping) genes, otherwise `FALSE` or empty. Same value in every well of a target. Written by the app when a target is marked HK. |
| *anything else* | no | Sample variables, e.g. `condition`, `time`, `BR`, `species`. Names are free. |

One row per well. Each `plate` + `well` combination appears at most once. Empty wells may be listed with role `empty` or left out.

## Roles

| Role | `sample` | `target` | Meaning |
|---|---|---|---|
| `sample` | required | required | A cDNA sample measured for a target. |
| `noRT` | required | required | No-reverse-transcriptase control. `sample` is the ID of the sample whose RNA went into it, so it can be compared to its +RT wells. |
| `NTC` | empty | required | No-template (water) control. |
| `IPC` | optional | required | Inter-plate calibrator. `sample` names the calibrator if several are used. |
| `std` | optional | required | Standard: one step of a dilution series, for primer efficiency. `dilution` gives the fold dilution. `sample` may name the template (e.g. the cDNA pool). |
| `empty` | empty | empty | Nothing loaded. |

Role names are case-insensitive on reading (`nort`, `NoRT` → `noRT`).

## Sample variables

Any column that isn't one of the five above (or `dilution`, `primer`, `reference`) describes the sample: condition, timepoint, biological replicate, treatment, species, and so on. Names and values are free, and change between experiments as needed.

Rules:

- Within one file, a sample ID always has the same values for its sample variables.
- Variables are filled for `sample` and `noRT` wells (same values as the sample). They may be left empty for `NTC`, `IPC` and `empty` wells.
- Reserved for analysis output, don't use as sample variables: `cq`, `nondetect`, `outlier`, `dct`, `tech_rep`, `efficiency`.

## Technical replicates

There is no technical-replicate column. Technical replicates are inferred:

- **Wells on one plate** with the same `sample`, `target` and `role` are technical replicates.
- **Plates as replicates**: when the same layout is run on several plates (TR1, TR2, TR3), list each plate's wells under its own `plate` ID. Whether plates count as technical replicates of each other is decided at analysis time, not in the file.

## Example

```
#cqpid layout v1
plate,well,role,sample,target,condition,time,BR
1,A01,sample,S1,gapdh,ctrl,0,1
1,A02,sample,S1,gapdh,ctrl,0,1
1,A03,sample,S1,gapdh,ctrl,0,1
1,A04,sample,S1,geneA,ctrl,0,1
1,G01,noRT,S1,gapdh,ctrl,0,1
1,G03,NTC,,gapdh,,,
1,H01,IPC,calib1,gapdh,,,
```

Full example: `spec/examples/layout_example.csv`.

## Dilution series (primer efficiency)

Standard wells use role `std` and a `dilution`. Wells with the same `target` and `dilution` are technical replicates. Example: 10-fold series of one cDNA pool in a column, two primer pairs, plus an NTC:

```
#cqpid layout v1
plate,well,role,sample,target,dilution
1,A01,std,pool1,gapdh,1
1,B01,std,pool1,gapdh,10
1,C01,std,pool1,gapdh,100
1,D01,std,pool1,gapdh,1000
1,A02,std,pool1,geneA,1
1,B02,std,pool1,geneA,10
1,C02,std,pool1,geneA,100
1,D02,std,pool1,geneA,1000
1,H01,NTC,,gapdh,
```

---

# Changes to this format

The format is versioned. A change that would make older files unreadable, or change their meaning, gets a new version number.

Additions within v1 (older files read exactly as before):

- Role `std` and column `dilution`, for dilution series (primer efficiency).
- Column `primer` (primer-pair label per target), written by the app for the master-mix tables.
- Column `reference` (housekeeping flag per target), written by the app.
