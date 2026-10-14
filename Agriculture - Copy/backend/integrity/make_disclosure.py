"""Fill the IDF-B invention disclosure template with the disclosure content.

The template at Downloads/Invention_Disclosure_Format_B (5).docx is used
verbatim: its styles, header table, second header block, TRL grid and closing
line are preserved, and only the placeholder body paragraphs under each
numbered heading are replaced.

Section 8 numbers are read from validation_results/validation_summary.json,
which is produced by ``python -m backend.validation.experiments``. The
generator refuses to emit a document if those numbers are absent, so a
disclosure can never carry placeholder or invented results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docx.table import Table
from docx.text.paragraph import Paragraph

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SUMMARY_PATH = BASE_DIR / "validation_results" / "validation_summary.json"
DEFAULT_TEMPLATE = Path.home() / "Downloads" / "Invention_Disclosure_Format_B (5).docx"

#: Body-text index of each numbered heading in the template.
HEADING_TEXTS = [
    "Title of the invention:",
    "Field /Area of invention:",
    "Prior Patents and Publications from literature",
    "Summary and background of the invention",
    "Objective(s) of Invention",
    "Working principle of the invent",
    "Description of the invention in detail",
    "Experimental validation results:",
    "What aspect(s) of the invention need(s) protection?",
    "What is Technology readiness level",
]


class Block:
    """One renderable piece of section content."""

    def __init__(self, kind: str, payload, style: str = "Body Text"):
        self.kind = kind  # "p" | "bullet" | "table" | "mono"
        self.payload = payload
        self.style = style


def para(text: str, bold: bool = False, italic: bool = False) -> Block:
    return Block("p", (text, bold, italic))


def head(text: str) -> Block:
    return Block("p", (text, True, False))


def bullet(text: str) -> Block:
    return Block("bullet", text)


def mono(text: str) -> Block:
    return Block("mono", text)


def table(rows: Sequence[Sequence[str]], widths: Optional[Sequence[int]] = None, header: bool = True) -> Block:
    return Block("table", (list(rows), widths, header))


# ---------------------------------------------------------------------------
# XML placement helpers
# ---------------------------------------------------------------------------


def _clear_between(body, start_idx: int, end_idx: int) -> List:
    """Remove the template's empty placeholder paragraphs in [start, end)."""

    removed = []
    for child in list(body.iterchildren())[start_idx + 1 : end_idx]:
        tag = child.tag.split("}")[-1]
        if tag == "p" and not Paragraph(child, None).text.strip():
            removed.append(child)
            body.remove(child)
    return removed


def _insert_after(anchor, new_elements: List) -> None:
    ref = anchor
    for element in new_elements:
        ref.addnext(element)
        ref = element


def _build_paragraph(doc, block: Block):
    style = block.style
    if block.kind == "mono":
        p = doc.add_paragraph(style="Body Text" if "Body Text" in [s.name for s in doc.styles] else None)
        run = p.add_run(block.payload)
        run.font.name = "Courier New"
        run.font.size = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        return p
    if block.kind == "bullet":
        p = doc.add_paragraph(style="List Paragraph" if "List Paragraph" in [s.name for s in doc.styles] else None)
        p.add_run("•  " + block.payload)
        p.paragraph_format.space_after = Pt(3)
        return p
    text, bold, italic = block.payload
    p = doc.add_paragraph(style=style)
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    p.paragraph_format.space_after = Pt(6)
    return p


def _build_table(doc, block: Block):
    rows, widths, header = block.payload
    tbl = doc.add_table(rows=len(rows), cols=len(rows[0]))
    try:
        tbl.style = "Table Grid"
    except KeyError:
        pass
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            run = p.add_run(str(value))
            run.font.size = Pt(7.5)
            if header and i == 0:
                run.bold = True
    if widths:
        for j, w in enumerate(widths):
            for row in tbl.rows:
                row.cells[j].width = Pt(w)
    return tbl


def fill_section(doc, body, heading_index: int, next_heading_index: int, blocks: List[Block]) -> None:
    children = list(body.iterchildren())
    heading_el = children[heading_index]
    _clear_between(body, heading_index, next_heading_index)

    new_elements = []
    for block in blocks:
        if block.kind == "table":
            tbl = _build_table(doc, block)
            new_elements.append(tbl._element)
        else:
            p = _build_paragraph(doc, block)
            new_elements.append(p._element)
    _insert_after(heading_el, new_elements)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


def load_summary(path: Path = SUMMARY_PATH) -> Dict:
    if not path.exists():
        raise SystemExit(
            f"validation summary not found at {path}.\n"
            "Run:  python3 -m backend.validation.experiments\n"
            "Section 8 is filled from measured output and is never written from memory."
        )
    with path.open() as fh:
        return json.load(fh)


def section_1() -> List[Block]:
    return [
        para(
            "PROVENANCE-CONDITIONED UNCERTAINTY CALIBRATION AND CROSS-SOURCE CONSISTENCY "
            "DETECTION IN PREDICTIVE INFERENCE OVER MIXED-QUALITY INPUT SOURCES",
            bold=True,
        ),
        para(
            "A computer-implemented method for producing a prediction and a "
            "source-conditioned uncertainty interval from a fixed, previously trained "
            "predictive model, in which the calibration residuals are partitioned by the "
            "provenance state of the input acquisition pipeline; the partitions are "
            "populated by counterfactually degrading held-out observations through the "
            "system's own documented fallback chain; sparse partitions fall back to pooled "
            "residuals through a backoff ladder with a stated inflation; disagreement "
            "between independent sources is detected and used to select the uncertainty "
            "treatment without altering the point estimate; and every inference is "
            "recorded in a hash-chained ledger entry that is sufficient to reproduce the "
            "output without re-querying any external source."
        ),
        para(
            "Working title of the prototype: AgriTwin India (sensor-free agricultural "
            "digital twin, Ariyalur, Tamil Nadu). The invention is domain-agnostic; the "
            "agricultural setting is one worked example and one validation embodiment."
        ),
    ]


def section_2() -> List[Block]:
    return [
        para(
            "Field: uncertainty quantification and reliability engineering for machine "
            "learning inference; provenance-aware predictive systems; remote-sensing and "
            "environmental data fusion; reproducible machine learning."
        ),
        para(
            "The subject matter is a computer-implemented data-processing method. It does "
            "not actuate any physical device, does not control irrigation or machinery, "
            "and requires no field hardware. Its inputs are stored numerical series and "
            "retrieved records; its outputs are numerical predictions, uncertainty bounds, "
            "machine-readable status codes and structured audit records.",
        ),
        para("Applicable beyond agriculture: any predictive system that draws inputs from more than one source of differing reliability."),
    ]


def section_3(summary: Dict) -> List[Block]:
    n = summary["n_seasons"]
    rows = [
        [
            "Ref",
            "Citation",
            "Subject",
            "Relevance to this invention",
        ],
        [
            "P1",
            "Vovk, Lindsay, Nouretdinov, Gammerman, 'Mondrian Confidence Machine', "
            "Royal Holloway COMPNET WP No. 4 (2003); Vovk, Gammerman, Shafer, 'Algorithmic "
            "Learning in a Random World', Springer (2005); Vovk, 'Conditional validity of "
            "inductive conformal predictors', ACML 2012, PMLR v25, pp. 475-490",
            "Taxonomy-conditional conformal prediction with type-wise validity",
            "Establishes that conditional conformal is fully general in the taxonomy. "
            "Anticipates any claim of the form 'partition residuals by a key'. The "
            "invention must therefore be argued at the level of the specific key, the "
            "population mechanism and their coupling, not at the level of partitioning.",
        ],
        [
            "P2",
            "Zaffran, Dieuleveut, Josse, Romano, 'Conformal Prediction with Missing Values', "
            "AISTATS 2023, PMLR v202",
            "Builds a calibration set by degrading clean points so that the mask of the "
            "test point is mimicked ('missing data augmentation')",
            "Closest prior art to the counterfactual-degradation element. The distinction "
            "relied upon is that its degradation operator is a generic feature mask acting "
            "on absentness, whereas here the operator is the system's declared fallback "
            "chain, acting on values that are present but produced in a degraded state.",
        ],
        [
            "P3",
            "Melki, Bombrun, Da Costa, 'Group-Conditional Conformal Prediction via "
            "Quantile Regression Calibration for Crop and Weed Classification', arXiv:2308.15094; "
            "and 'Towards Group-Conditional Coverage Guarantees via Group-Invariant "
            "Representations', PMLR v329 (2026)",
            "Group-conditional conformal prediction in precision agriculture, keyed on "
            "acquisition-condition metadata",
            "Demonstrates that conditioning on acquisition metadata is an active published "
            "line in this exact application domain. The claim is therefore narrowed to "
            "provenance/fallback state and not to acquisition metadata generally.",
        ],
        [
            "P4",
            "US20220091915A1, Dell Products L.P., filed 2020-09-21, published 2022-03-24; "
            "CN121902329A, filed 2026-03-25, published 2026-04-21",
            "Conformal confidence measure conditioned on a credibility measure indicating "
            "the quality of the monitoring data",
            "Establishes that 'condition a conformal output on input data quality' is "
            "claimed in the patent literature. Anticipates a broad claim on that framing.",
        ],
        [
            "P5",
            "Devos et al., 'Assessing Spatial Limits of Sentinel-2 Data on Arable Crops in "
            "the Context of Checks by Monitoring', Remote Sensing 12(14), 2195 (2020)",
            "Derives per-parcel reliability criteria for Sentinel-2 from the count of clean "
            "pixels inside a half-pixel negative buffer",
            "Anticipates using a buffer-derived support statistic as a reliability signal in "
            "arable crops. Distinguishes the invention, which uses the residual from a fitted "
            "scale trend across a ladder of radii rather than a pixel count at one radius.",
        ],
        [
            "P6",
            "Fan et al., 'Scaling Effect of Area-Averaged NDVI: Monotonicity along the "
            "Spatial Resolution', Remote Sensing 4(1), 160 (2012); Openshaw, 'The "
            "Modifiable Areal Unit Problem', Geo Abstracts (1984)",
            "Area-averaged vegetation index varies monotonically with spatial resolution "
            "within a resolution class",
            "Shows a naive cross-radius stability statistic measures the scale effect rather "
            "than representativeness. The invention de-trends the ladder against the fitted "
            "scale trend precisely to avoid this.",
        ],
        [
            "P7",
            "Glahn and Lowry, 'The use of model output statistics (MOS) in objective weather "
            "forecasting', J. Appl. Meteorol. 11, 1203-1211 (1972); Gneiting, Raftery, "
            "Westveld, Goldman, 'Calibrated Probabilistic Forecasting Using Ensemble Model "
            "Output Statistics and Minimum CRPS Estimation', Monthly Weather Review 133(5), "
            "1098-1118 (2005)",
            "Horizon-dependent weighting of forecasts fitted against verifying observations",
            "Anticipates any standalone claim to weighting forecast terms by historical "
            "error. Such weighting appears here only as a component.",
        ],
        [
            "P8",
            "Cross and Zuber, 'Prediction of Flowering Dates in Maize Based on Different "
            "Methods of Estimating Thermal Units', Agronomy Journal 64, 351 (1972); "
            "Hodges and French, 'SOYPHEN', Agronomy Journal (1985); 'Phenology-adaptive "
            "machine learning for early mapping of field-scale corn crop yield', "
            "Precision Agriculture (2026), doi:10.1007/s11119-026-10428-4; T3S, "
            "arXiv:2506.12885",
            "Thermal-time alignment of observations and yields",
            "Anticipates any standalone claim to aligning by growing degree days, including "
            "in remote-sensing yield pipelines. What is not found in the literature is "
            "alignment of the current season against the historical expectation at matched "
            "thermal time, weighted by trajectory similarity, with a forecast-inclusive path.",
        ],
        [
            "P9",
            "Maraun, 'Bias Correcting Climate Change Simulations - a Critical Review', "
            "Current Climate Change Reports 2, 23-29 (2016); Maraun et al., Nature Climate "
            "Change 7, 532-533 (2017)",
            "Residual- and bias-fitted correction bounded by historical error structure; "
            "critique of cross-validation as insufficient evaluation",
            "Anticipates bounded, residual-fitted bias correction. Also supplies the "
            "objection that cross-validating marginal properties is not sufficient "
            "evaluation of a bias correction; the validation protocol below is designed "
            "with that objection in view.",
        ],
        [
            "P10",
            "Dempster and Shafer, 'A Mathematical Theory of Evidence' (1976); Sarabi-Jamab "
            "and Araabi, 'How to decide when the sources of evidence are unreliable: a "
            "multi-criteria discounting approach in the Dempster-Shafer theory', Information "
            "Sciences 448-449, 233-248 (2018); 'Ambiguous Agricultural Drought', Remote "
            "Sensing 13(10), 1990 (2021)",
            "Multi-source conflict measurement and reliability discounting; documented "
            "asynchrony between meteorological and vegetation drought",
            "Anticipates both the detection of source disagreement and, in agriculture, the "
            "specific finding that weather-derived and vegetation-derived stress diverge. "
            "Only the use of that state as a calibration key is claimed.",
        ],
        [
            "P11",
            "'Record and Replay Methods for Software Engineering Reproducibility: A "
            "Cross-Layer Survey and Taxonomy', ACM, doi:10.1145/3820002.3828587; Gebru et "
            "al., 'Datasheets for Datasets', CACM 64(12), 86-92 (2021), "
            "doi:10.1145/3458723",
            "Reproducibility taxonomy, boundary-aware replay, dataset documentation",
            "Establishes that the closure problem in replay is recognised and unsolved, and "
            "that documentation standards do not claim replay sufficiency. The claimed "
            "property is that the record alone reproduces the output without refetching, "
            "because upstream data mutates.",
        ],
        [
            "P12",
            "Indian patent applications, publication journals as listed in section 3.1 "
            "(unconfirmed - see note)",
            "Sensor-based digital twins, federated and blockchain agricultural platforms, "
            "multi-modal yield models, ecological-instability crop recommendation",
            "Nearest Indian filings in the subject domain. None is directed to "
            "provenance-conditioned uncertainty calibration. Existence could not be "
            "confirmed; see the verification note below.",
        ],
    ]
    blocks: List[Block] = [
        head("3.1  Indian patent filings in the subject domain - verification status"),
        para(
            "The following applications were supplied as related prior art. The publication "
            "journal numbers and dates supplied for each were checked against the public "
            "Indian Patent Office journal index and are consistent with it, and the "
            "application serial numbers are in correct chronological order relative to "
            "independently located anchor applications. However, the existence of the "
            "applications and the accuracy of their titles could not be confirmed, because "
            "the official InPASS register requires an interactive captcha and the relevant "
            "journal issues are not available through any open full-text index. No search of "
            "any open patent database returned these records.",
        ),
        para(
            "They are therefore recorded as UNCONFIRMED. Each must be verified by a person "
            "through InPASS, or by direct download of the journal PDFs, before any of them "
            "is relied upon in a filed application. They are not treated here as "
            "establishing or destroying novelty; the novelty position in section 4 rests on "
            "the verified non-patent literature in section 3.2 and on the absence of "
            "anticipating art in the searches reported there.",
        ),
        table(
            [
                ["Supplied application no.", "Supplied journal / date", "Verification outcome"],
                ["20251102911", "50/2025, 12 Dec 2025", "Structurally defective: 11 digits. Every Indian application number is 12 digits. Not usable as cited."],
                ["202641088624", "33/2026, 14 Aug 2026", "Unconfirmed. No structural defect."],
                ["202641061848", "22/2026, 29 May 2026", "Unconfirmed. No structural defect."],
                ["202641046808", "17/2026, 24 Apr 2026", "Unconfirmed. No structural defect."],
                ["202641094834", "37/2026, 11 Sep 2026", "Unconfirmed. No structural defect."],
                ["202641088127", "30/2026, 24 Jul 2026", "Unconfirmed. Filed-to-published gap of 4 days is below the shortest gap observed in primary sources (10 days)."],
                ["202641086877", "33/2026, 14 Aug 2026", "Unconfirmed. No structural defect."],
                ["202641113494", "39/2026, 25 Sep 2026", "Unconfirmed. Filed-to-published gap of 3 days is below the observed minimum and is not credible without an early-publication request."],
                ["202641090862", "32/2026, 7 Aug 2026", "Unconfirmed. Borderline gap."],
                ["202641103136", "36/2026, 4 Sep 2026", "Unconfirmed. Borderline gap."],
            ],
            widths=[70, 75, 275],
        ),
        para(
            "Note on Indian publication practice: the earlier assumption that publication "
            "follows filing by approximately eighteen months was tested against primary "
            "sources and found to be wrong as a general rule. Early publication at "
            "applicant request is routine, and filed-to-published gaps of 10 to 43 days "
            "were confirmed in actual journals. Short gaps are therefore not by themselves "
            "evidence of fabrication, although a 3 or 4 day gap remains implausible.",
        ),
        head("3.2  Non-patent and academic prior art (verified)"),
        para(
            "The table below is the operative prior-art record. Every component named in the "
            "original proposal is anticipated by published work taken individually. The "
            "inventive concept claimed is the conjunction described in section 4.2, not any "
            "component.",
        ),
        table(rows, widths=[26, 145, 95, 154]),
        head("3.3  Searches that returned nothing"),
        para(
            "The following constructs were searched for in the United States, European and "
            "international patent collections and returned no hit: conditioning a prediction "
            "interval on an enumerated live / cached / forecast-substitute / "
            "climatology-fallback / proxy provenance state; synthesising a conformal "
            "calibration set by degrading held-out inputs through a production fallback "
            "chain; detection of conflict between weather-derived stress evidence and "
            "satellite vegetation evidence used as an uncertainty-routing key; use of "
            "cross-radius vegetation-index stability as a calibration-group key; and "
            "hash-chained inference ledgers binding external source requests.",
        ),
        para(
            f"These were roughly eight queries, not an exhaustive search. They establish the "
            f"absence of an obvious blocker, not the absence of prior art. A dedicated "
            f"patentability search by a qualified searcher remains required before filing. "
            f"The validation embodiment below rests on {n} real crop-seasons.",
            italic=True,
        ),
    ]
    return blocks


def section_4() -> List[Block]:
    return [
        head("4.1  Technical problem"),
        para(
            "A fixed predictive model, trained once and then frozen, produces an interval "
            "that is identical in character whether its inputs were retrieved live moments "
            "ago or reconstructed from long-run averages because the feed was down. The "
            "interval does not know which of these happened. This produces four specific "
            "computer-level failures:",
        ),
        bullet(
            "Silent substitution. When a live source fails, the pipeline substitutes a "
            "fallback and returns the same narrow, confident-looking interval it would have "
            "returned had the substitution not occurred."
        ),
        bullet(
            "Unconditioned calibration. A pooled residual set averages over input-quality "
            "states that behave differently, so the interval is simultaneously too wide "
            "where inputs are trustworthy and too narrow where they are not."
        ),
        bullet(
            "Undetected contradiction. Two independent sources describing the same field "
            "can disagree, and nothing in the pipeline notices, so a confident point "
            "estimate is issued on a contradictory input set."
        ),
        bullet(
            "Irreproducibility. The inputs that produced a published figure are not "
            "recorded in a form that permits recomputation, because upstream sources have "
            "since changed or become unavailable."
        ),
        para(
            "These are reliability and calibration defects in a computational process. They "
            "are distinct from the agricultural question of what advice to give a farmer, "
            "and the method does not address that question."
        ),
        head("4.2  The gap that is claimed"),
        para(
            "Every individual ingredient is known art (section 3.2). The claimed "
            "contribution is the following specific coupling, which was not found in any "
            "search conducted:",
        ),
        para(
            "A single declared fallback chain serves two simultaneous roles in one method. "
            "It is the operator by which held-out observations are degraded to populate the "
            "calibration partitions, and it is the definition of the partition key. Because "
            "real observations in a degraded state do not occur in nature, the calibration "
            "populations cannot be obtained any other way; and because the taxonomy and the "
            "degradation operator are the same artefact, a partition cannot drift out of "
            "correspondence with the conditions it claims to represent. Applied to a model "
            "that is never retrained, with vegetation quality and cross-source disagreement "
            "as additional key axes, and with every inference written to a ledger entry "
            "sufficient to reproduce it without refetching.",
        ),
        head("4.3  What is expressly not claimed"),
        para(
            "Not claimed: an agricultural digital twin; a crop-yield prediction system; a "
            "farm advisory system; growing degree days; horizon-weighted forecast blending; "
            "bounded residual-fitted bias correction; cross-source conflict detection as "
            "such; the use of a buffer statistic as a quality signal as such; or "
            "provenance recording or hash chaining as such.",
        ),
        para(
            "No physical sensor, actuator, field device, irrigation control, blockchain or "
            "federated learning arrangement is described, because none is present in the "
            "system that produced the results below. Adding such elements would not be "
            "accurate to the embodiment.",
            italic=True,
        ),
    ]


def section_5() -> List[Block]:
    return [
        para(
            "1. To produce, from a fixed predictive model whose parameters are not updated, "
            "an uncertainty interval whose width is a function of the provenance state of "
            "the inputs that produced it, such that the interval narrows where the inputs "
            "are trustworthy and widens where they are not."
        ),
        para(
            "2. To make the partition populations obtainable at all, by generating them "
            "mechanically from held-out observations routed through the system's declared "
            "fallback chain, so that no population depends on a degraded condition "
            "occurring naturally."
        ),
        para(
            "3. To detect disagreement between independent sources and use that "
            "disagreement to select the uncertainty treatment, without permitting the "
            "disagreement to alter the point estimate directly."
        ),
        para(
            "4. To record each inference so that it can be reproduced exactly from the "
            "record alone, without re-querying any external source, and so that alteration "
            "of any recorded value is detectable."
        ),
        para(
            "5. To state honestly, per inference, whether the interval delivered carries a "
            "finite-sample guarantee or is a heuristic widening, so that a consumer of the "
            "output cannot mistake one for the other."
        ),
    ]


def section_6() -> List[Block]:
    return [
        para(
            "The method is a fixed sequence of stages applied to one prediction. Stages 1 "
            "to 7 construct inputs; stages 8 to 11 select and apply the output. No stage "
            "retrains, refits or reweights the base model."
        ),
        table(
            [
                ["Stage", "Operation", "Purpose"],
                ["1", "Assign each external source a provenance record: category (live, cached, forecast, historical fallback, proxy), acquisition time, data age, forecast horizon, missing-data treatment, spatial radius, cloud and valid-pixel fractions, and a SHA-256 digest of the retrieved payload.", "Convert a human-readable source label into a machine-comparable, hashable state."],
                ["2", "Accumulate base-temperature thermal time over observed days, with upper-cap convention, over the season to date plus the forecast horizon.", "Express developmental progress as a coordinate independent of sowing date."],
                ["3", "For each historical season, find the calendar date at which that season itself reaches the current accumulated thermal time; truncate it there; compute its rainfall, ET0, maximum temperature and heat days over that thermal prefix.", "Build the historical expectation over an equivalent developmental window rather than a calendar window."],
                ["4", "Weight the truncated historical seasons by similarity of their truncated cumulative-rainfall trajectory to the median analogue.", "Give less weight to years that were already anomalous at this developmental stage."],
                ["5", "Weight each forward forecast day by a measured skill weight interpolated from a forecast-error-versus-lead-time curve, and form the anomaly vector of the current season against the step-3 expectation.", "Produce the anomaly vector, discounting projected weather as its reliability decays."],
                ["6", "Sample the vegetation index over an adaptive ladder of buffer radii, fitted against the systematic scale trend, and take the residual as the spatial-trust signal. Collapse valid-pixel fraction and spatial trust into a quality band.", "Estimate how representatively a point sample describes the field without a parcel boundary, without being dominated by the known monotone scale effect."],
                ["7", "Compare the weather stress flag with the vegetation flag and emit a conflict code. Quality and coverage codes are kept separate from genuine disagreement codes.", "Detect that the input set is internally inconsistent, and route on it without changing the point estimate."],
                ["8", "Form the composite provenance key: weather degradation state, vegetation quality band, conflict state.", "Select the residual population."],
                ["9", "Select a partition by backoff: exact cell; then progressively drop one conditioning axis; then pooled. Apply a stated inflation on any backed-off result and record which level of guarantee applies.", "Obtain a usable quantile when cells are sparse, without claiming a guarantee that backoff does not provide."],
                ["10", "Apply a ridge-fitted correction, bounded by the empirical distribution of historical base-model residuals, and record per-component attribution.", "Move the point estimate in the direction the fitted residual relationship indicates, without unbounded extrapolation."],
                ["11", "Write the ledger entry: canonicalised input values, provenance records, thermal-time value, expectation, anomaly vector, forecast weights, vegetation result, conflict code, correction components, selected partition and quantile, output, and a chain-linked hash.", "Make the inference reproducible and tamper-evident without refetching."],
            ],
            widths=[30, 240, 150],
        ),
        para(
            "Statistical qualification, stated as part of the working principle and not as a "
            "footnote: the finite-sample coverage guarantee of a split-conformal quantile "
            "holds only when the selected partition contains at least ceil(1/alpha) - 1 "
            "residuals exchangeable with the test point. Below that floor the quantile is an "
            "order statistic with no guarantee. When backoff reaches the pooled set, the "
            "applied inflation factor is a monotone widening and does not restore the "
            "guarantee. The method therefore emits an explicit guarantee level with every "
            "interval, and the validation below reports intervals of both kinds separately.",
        ),
    ]


def load_worked_example(path: Path = None) -> Dict:
    p = path or (BASE_DIR / "validation_results" / "worked_example.json")
    if not p.exists():
        raise SystemExit(
            f"worked example not found at {p}.\n"
            "Run:  python3 -m backend.validation.worked_example\n"
            "Section 7.2 quotes a captured ledger entry and is never written from memory."
        )
    return json.loads(p.read_text())


def section_7(summary: Dict, example: Dict) -> List[Block]:
    res = example["result"]
    entry = example["ledger_entry"]
    thermal = res["thermal_time"]
    veg = res["vegetation"]
    stab = veg.get("stability") or {}
    sel = res["calibration_selection"]
    corr = res["correction"]

    def g(d, *path, default="n/a"):
        cur = d
        for key in path:
            if cur is None:
                return default
            cur = cur.get(key) if isinstance(cur, dict) else None
        return default if cur is None else cur

    skill = example.get("skill_curve", {})
    skill_row = "   ".join(
        f"lead {k} -> {v:.3f}" for k, v in sorted(skill.items(), key=lambda kv: int(kv[0]))
    )

    prov = {p["source_id"]: p for p in entry["provenance"]}

    return [
        head("7.1  System architecture"),
        mono(
            "provenance.py    SourceRecord, SourceCategory, ProvenanceLedger\n"
            "                 structured, hashable replacement for free-text source labels\n"
            "thermal_time.py  daily_gdd, accumulate_gdd, prepare_seasons,\n"
            "                 thermal_time_expectation_prepared, persistence_skill_curve\n"
            "                 thermal-time alignment and measured horizon skill weighting\n"
            "vegetation.py    support_stability, ndvi_quality_band, simulate_ladder\n"
            "                 de-trended cross-radius spatial trust\n"
            "conflict.py      detect() -> ConflictCode\n"
            "                 cross-source agreement classification\n"
            "calibration.py   QualityKey, CalibrationStore (stratified backoff), conformal_quantile\n"
            "                 provenance-conditioned residual selection\n"
            "ledger.py        LedgerEntry, InferenceLedger, replay(), canonical_json\n"
            "                 replay-sufficient hash-chained record\n"
            "engine.py        IntegrityEngine.infer(), fit_correction_model()\n"
            "                 orchestration; base model is never updated\n"
            "integrity_service.py   serves the engine from the running application\n"
            "validation/      degrade.py, experiments.py, worked_example.py\n"
            "                 counterfactual degradation harness, leave-one-season-out\n"
            "                 scoring, and capture of the worked example below"
        ),
        head("7.2  Worked example - one captured inference"),
        para(
            f"Captured from an actual run by `backend.validation.worked_example` for season "
            f"{example['season']} under the {example['regime'].replace('_', ' ')} regime. "
            f"Every value below is read out of the ledger entry that run produced; none of "
            f"it is written by hand. The recorded actual yield was "
            f"{example['actual_yield']:.2f} t/ha."
        ),
        mono(
            f"base_model_version : {entry['base_model_version']}   (parameters unchanged)\n"
            f"weather provenance : category={prov.get('weather', {}).get('category_label')}, "
            f"age={prov.get('weather', {}).get('data_age_hours', 0) / 24.0:.0f} d, "
            f"missing={prov.get('weather', {}).get('missing_treatment')}\n"
            f"vegetation prov.   : radius={prov.get('vegetation', {}).get('radius_m')} m, "
            f"valid_pixel={prov.get('vegetation', {}).get('valid_pixel_pct')}\n"
            f"provenance digest  : {entry['provenance_digest'][:32]}...\n"
            f"thermal time       : current_gdd={thermal['current_gdd']} degC, "
            f"base={thermal['base_temp_c']} degC\n"
            f"                    expectation drawn from "
            f"{thermal['historical_expectation']['n_analogues']} analogue seasons, each "
            f"truncated at its own date of equal accumulated thermal time\n"
            f"expectation        : rainfall {thermal['historical_expectation']['total_rainfall_mm']} mm, "
            f"ET0 {thermal['historical_expectation']['total_et0_mm']} mm, "
            f"tmax {thermal['historical_expectation']['avg_temp_max']} degC, "
            f"heat {thermal['historical_expectation']['heat_days']} d\n"
            f"anomaly vector     : rainfall {g(res, 'anomaly_vector', 'rainfall_pct')} %, "
            f"ET0 {g(res, 'anomaly_vector', 'et0_pct')} %, "
            f"tmax {g(res, 'anomaly_vector', 'temp_max_c')} degC, "
            f"heat {g(res, 'anomaly_vector', 'heat_days')} d\n"
            f"forecast weights   : "
            + skill_row
            + f"\n"
            f"spatial trust      : radii {stab.get('radii_m')}\n"
            f"                    trend_slope={stab.get('trend_slope')}, R2={stab.get('trend_r2')}, "
            f"residual_rms={stab.get('residual_rms')}\n"
            f"                    normalised_residual={stab.get('normalised_residual')}, "
            f"spatial_trust={stab.get('spatial_trust')} -> band '{veg.get('quality_band')}'\n"
            f"conflict           : {g(res, 'conflict', 'code')}\n"
            f"                    {g(res, 'conflict', 'detail')}\n"
            f"quality key        : {res['quality_key']}\n"
            f"partition selected : {sel['partition_label']}  (n={sel['n_residuals']}, floor=20)\n"
            f"backoff path       : {', '.join(sel['backoff_path'])}\n"
            f"guarantee          : {sel['guarantee_level']}, inflation {sel['inflation_applied']}\n"
            f"correction         : total {corr['total_pct']:+.4f} % "
            f"(raw {corr['raw_total_pct']:+.4f} %, bounded={corr['was_bounded']})\n"
            f"                    per-component %: "
            + ", ".join(f"{k} {v:+.5f}" for k, v in corr["components_pct"].items())
            + f"\n"
            f"bounds             : {corr['bounds_pct'][0]:+.4f} % to {corr['bounds_pct'][1]:+.4f} %\n"
            f"output             : {res['corrected_prediction_t_per_ha']} t/ha  "
            f"interval [{res['interval']['lower_bound']}, {res['interval']['upper_bound']}], "
            f"half-width {res['interval']['half_width']}\n"
            f"replay             : reproduced={example['replay']['reproduced']}\n"
            f"ledger             : entry_hash={entry['entry_hash'][:32]}...\n"
            f"                      previous_hash={entry['previous_hash'][:32]}..."
        ),
        para(
            f"Two features of this entry are worth reading closely. First, the guarantee is "
            f"reported as '{sel['guarantee_level']}' and not as a conformal interval, even "
            f"though the selected stratum contained {sel['n_residuals']} residuals and met the "
            f"size floor. That is because the exact composite cell was too sparse and the "
            f"stratum was reached by backoff, which merges several cells and so does not "
            f"restore the exchangeability condition the guarantee rests on. The system says so "
            f"rather than presenting the number as calibrated.",
            italic=True,
        ),
        para(
            f"Second, the weather record came from the historical fallback while the canopy "
            f"read as normal, so a conflict code was emitted. The point estimate was not moved "
            f"by that disagreement; the code changed only which residual population the "
            f"interval was drawn from. Note also the correction bound of "
            f"{corr['bounds_pct'][0]:+.2f} % to {corr['bounds_pct'][1]:+.2f} %: the lower "
            f"bound is inherited from a single season whose recorded yield was zero, because "
            f"the 1 % quantile of 35 relative residuals is the minimum of them. That is a "
            f"real weakness of a data-derived bound on a sample this small, and it is "
            f"disclosed rather than hidden.",
            italic=True,
        ),
        head("7.3  Why the vegetation stability metric is de-trended"),
        para(
            "Area-averaged vegetation index is known to vary monotonically with spatial "
            "resolution. A ladder sampled at 90, 180, 360, 720 and 1440 m will therefore "
            "show a downward trend even over a perfectly uniform field. Two consequences "
            "follow, and both are handled explicitly:"
        ),
        bullet(
            "The raw spread of the ladder cannot be the quality signal, because it is "
            "dominated by the scale trend. The method regresses index on log-radius across "
            "the ladder and uses the residual about that fit as the signal."
        ),
        bullet(
            "The ladder cannot be stopped on a raw-delta criterion either, for the same "
            "reason: a uniform field would never appear to converge. Convergence is judged "
            "on what an additional radius contributes beyond the fitted trend."
        ),
        head("7.4  Measured forecast skill weights"),
        para(
            "No archived numerical weather prediction output exists for this station. The "
            "weights are therefore measured from a persistence pseudo-forecast on the "
            "station's own 4,688-day archive: the value observed at issue time is carried "
            "forward h days and scored against what actually occurred. They are real "
            "measurements of a weak forecast; a deployment would substitute a curve computed "
            "from archived forecast-versus-observation pairs without changing any downstream "
            "interface."
        ),
        table(
            [["Lead time (days)"] + [k for k in sorted(skill, key=int)],
             ["Skill weight"] + [f"{skill[k]:.4f}" for k in sorted(skill, key=int)]],
            widths=[95] + [34] * len(skill),
        ),
        head("7.5  Honest limits of the embodiment"),
        bullet(
            "The weather side and the yield targets are real. The vegetation side is "
            "simulated: no NDVI time series exists for these farms, and the production "
            "database holds exactly one observed row. Every result that depends on the "
            "vegetation axis is therefore a simulation result and is reported as such."
        ),
        bullet(
            "The dataset is 36 crop-seasons from one district over 2009-2019, with one "
            "observation per season and no spatial replication. Per-group sample sizes are "
            "small, and coverage estimates carry wide binomial uncertainty."
        ),
        bullet(
            "Calibration residuals for a season are correlated across regimes, because the "
            "same season is re-run ten times. Effective sample size is below the nominal "
            "count, which is one reason the minimum partition size is set at 20 rather than "
            "the theoretical floor of 9."
        ),
        bullet(
            "The correction improves bias but not point error on this dataset (section 8). "
            "It is retained because it is part of the claimed method and because its added "
            "variance is what the conditioning step measures and absorbs, but a deployment "
            "may set it to zero and retain the calibration and the ledger unchanged."
        ),
    ]


def section_8(summary: Dict) -> List[Block]:
    ov = summary["overall"]
    cd = summary["conflict_detection"]
    rp = summary["replay"]
    tm = summary["tamper"]
    regimes = list(summary["by_regime"].items())

    rows = [["Regime", "Coverage, pooled base", "Coverage, proposed", "Width, pooled base", "Width, proposed", "Cal. error, base", "Cal. error, proposed"]]
    for name, entry in regimes:
        rows.append(
            [
                name.replace("_", " "),
                f"{entry['base']['coverage']:.4f}",
                f"{entry['engine']['coverage']:.4f}",
                f"{entry['base']['mean_width']:.4f}",
                f"{entry['engine']['mean_width']:.4f}",
                f"{entry['base']['calibration_error']:.4f}",
                f"{entry['engine']['calibration_error']:.4f}",
            ]
        )

    abl = summary["ablations"]
    abl_rows = [["Variant", "Point MAE (t/ha)", "Mean bias (t/ha)", "n"]]
    for name in sorted(abl):
        label = name.replace("_", " ")
        abl_rows.append([label, f"{abl[name]['point_mae']:.4f}", f"{abl[name]['mean_bias']:+.4f}", str(abl[name]["n"])])

    coef = summary.get("correction_coefficients", {}).get("coefficients", {})

    return [
        para(
            f"Protocol: leave-one-season-out over all {summary['n_seasons']} real Ariyalur "
            f"crop-seasons. For each held-out season the ridge correction is re-fitted and "
            f"the calibration store is rebuilt from the remaining seasons only, with the "
            f"held-out season's own crop-year excluded from the thermal-time expectation. "
            f"That yields {summary['n_predictions']} scored predictions over "
            f"{len(summary['regimes'])} degradation regimes."
        ),
        para(
            "Three comparators are scored on identical held-out predictions: the base model "
            "with one pooled conformal margin (the behaviour of the current system); the "
            "current bounded rule overlay with the same pooled margin; and the proposed "
            "method.",
        ),
        head("8.1  Overall"),
        table(
            [
                ["Method", "Coverage (nominal 0.90)", "Mean interval width (t/ha)", "Calibration error", "Point MAE (t/ha)"],
                ["Base model, one pooled margin", f"{ov['base']['coverage']:.4f}", f"{ov['base']['mean_width']:.4f}", f"{ov['base']['calibration_error']:.4f}", f"{ov['base']['point_mae']:.4f}"],
                ["Bounded rule overlay, pooled margin", f"{ov['overlay']['coverage']:.4f}", f"{ov['overlay']['mean_width']:.4f}", f"{ov['overlay']['calibration_error']:.4f}", f"{ov['overlay']['point_mae']:.4f}"],
                ["Proposed method", f"{ov['engine']['coverage']:.4f}", f"{ov['engine']['mean_width']:.4f}", f"{ov['engine']['calibration_error']:.4f}", f"{ov['engine']['point_mae']:.4f}"],
            ],
            widths=[130, 78, 90, 66, 70],
        ),
        para(
            f"Read the two errors in opposite directions, because that is what they are. The "
            f"pooled baseline sits ABOVE nominal: coverage {ov['base']['coverage']:.4f} against "
            f"0.90, an error of {ov['base']['calibration_error']:.4f}. With 35 calibration "
            f"points and heavy-tailed residuals the 90 % split-conformal quantile is set by the "
            f"upper tail, so a single pooled constant is conservative. The proposed method sits "
            f"BELOW nominal: coverage {ov['engine']['coverage']:.4f}, an error of "
            f"{ov['engine']['calibration_error']:.4f}. On absolute calibration error the "
            f"proposed method is better by a factor of "
            f"{ov['base']['calibration_error'] / max(ov['engine']['calibration_error'], 1e-9):.2f}, "
            f"and it does so while producing a mean interval "
            f"{(1 - ov['engine']['mean_width'] / ov['base']['mean_width']) * 100:.1f} % "
            f"narrower ({ov['engine']['mean_width']:.4f} against "
            f"{ov['base']['mean_width']:.4f} t/ha).",
            bold=True,
        ),
        para(
            f"It would be an overstatement to describe that as hitting the nominal level. The "
            f"proposed method under-covers by {abs(ov['engine']['coverage'] - 0.90):.4f}; the "
            f"baseline over-covers by {abs(ov['base']['coverage'] - 0.90):.4f}. The claim made "
            f"is the narrower one: on this data the conditioning step produces a materially "
            f"sharper interval without a worse calibration error, and the sign of the residual "
            f"error would reverse under a different residual tail. A deployment that cared "
            f"about under-coverage specifically would need to raise the nominal level above "
            f"0.90, and this result does not show that it would then be well calibrated.",
            italic=True,
        ),
        para(
            f"Guarantee labelling: of the {summary['n_predictions']} delivered intervals, "
            f"{sum(summary['by_regime'][r]['guarantee_mix'].get('finite_sample_conformal', 0) for r in summary['by_regime'])} "
            f"came from a partition selected without backoff and carry the finite-sample "
            f"conformal guarantee; "
            f"{sum(summary['by_regime'][r]['guarantee_mix'].get('heuristic_inflated_pooled', 0) for r in summary['by_regime'])} "
            f"required backoff and are heuristic widenings with no guarantee. The coverage "
            f"figures above are averaged over both kinds and should not be read as a claim "
            f"about the conformal subset alone.",
        ),
        head("8.2  By degradation regime"),
        table(rows, widths=[104, 66, 58, 62, 58, 54, 62]),
        para(
            "The width behaviour is the designed one. In the fully trustworthy regime the "
            "proposed interval is narrower than the pooled constant, because it is drawn "
            "from a stratum in which errors are small. Under climatology fallback it is "
            "substantially wider, because it is drawn from a stratum in which errors are "
            "large. A single pooled constant cannot do both: it has one number and must be "
            "wrong in at least one of these regimes."
        ),
        head("8.3  Cross-source conflict detection"),
        table(
            [
                ["Metric", "Value"],
                ["Precision", f"{cd['precision']:.4f}"],
                ["Recall", f"{cd['recall']:.4f}"],
                ["F1", f"{cd['f1']:.4f}"],
                ["Accuracy", f"{cd['accuracy']:.4f}"],
                ["Confusion", f"TP={cd['tp']}, FP={cd['fp']}, FN={cd['fn']}, TN={cd['tn']}"],
            ],
            widths=[120, 120],
        ),
        para(
            f"Recall of {cd['recall']:.4f} is weak and is reported as such. The detector "
            f"uses fixed anomaly thresholds, so when a season is naturally stressed the "
            f"weather and vegetation evidence agree and no code is emitted, even though a "
            f"conflict was injected by the harness. A production version should test the "
            f"weather flag against a fitted seasonal distribution rather than a fixed "
            f"threshold. This result does not support a claim of reliable conflict "
            f"detection on its own.",
            italic=True,
        ),
        head("8.4  Deterministic reproducibility"),
        table(
            [
                ["Test", "Result"],
                ["Ledger entries replayed", f"{rp['checked']}"],
                ["Replayed bit-identical", f"{rp['reproduced']}"],
                ["Reproduction rate", f"{rp['rate']:.4f}"],
                ["Intact entry verifies", str(tm["intact_detected"])],
                ["Altered entry rejected", str(tm["tampered_detected_as_invalid"])],
            ],
            widths=[150, 110],
        ),
        para(
            "Replay reads the entry's own recorded values and shares no state with the "
            "inference path. A rate of 1.0 demonstrates that the record is sufficient on "
            "its own; it does not, and is not claimed to, prove that the external sources "
            "were correct at the time of retrieval. The chain is tamper-evident, not "
            "tamper-proof: a party able to rewrite every record can recompute a "
            "self-consistent chain. Binding the chain head to an external anchor would "
            "close that gap and is not implemented.",
        ),
        head("8.5  Component ablations"),
        table(abl_rows, widths=[130, 90, 90, 50]),
        para(
            f"Removing thermal-time alignment is the single most damaging ablation: mean "
            f"bias moves from {abl['engine_full']['mean_bias']:+.4f} to "
            f"{abl['no_thermal_time']['mean_bias']:+.4f} t/ha. Calendar-window alignment "
            f"leaves a large systematic bias because sowing-date drift is not accounted "
            f"for. Removing horizon weighting or the de-trended spatial metric degrades "
            f"point error by a smaller amount."
        ),
        para(
            f"The correction reduces bias from {abl['no_correction']['mean_bias']:+.4f} to "
            f"{abl['engine_full']['mean_bias']:+.4f} t/ha but increases point MAE from "
            f"{abl['no_correction']['point_mae']:.4f} to "
            f"{abl['engine_full']['point_mae']:.4f} t/ha. This is a genuine negative "
            f"result on point accuracy and is not concealed. The interpretation is that a "
            f"residual-fitted correction applied to a partial season reduces systematic "
            f"error while adding variance, and that on 36 seasons the variance term "
            f"dominates. The measurable benefit claimed for this invention is therefore "
            f"calibration and reproducibility, not point accuracy.",
            bold=True,
        ),
        para(
            f"Fitted correction coefficients (first fold, ridge on leave-one-out relative "
            f"residuals): "
            + ", ".join(f"{k} = {v:+.6g}" for k, v in coef.items())
            + ". Bounds are taken from the empirical 1 % / 99 % quantiles of the fitted "
            "relative residuals rather than chosen.",
        ),
        head("8.6  Validity conditions and what these numbers do not show"),
        bullet(
            f"{summary['n_seasons']} seasons give "
            f"{summary['n_seasons'] / max(1, len(summary['regimes'])):.0f} predictions per "
            f"regime per method. At that size the binomial standard error on a coverage "
            f"estimate near 0.90 is about 0.09, which is of the same order as the difference "
            f"between the two methods. The coverage comparison is therefore indicative only. "
            f"The stronger evidence in this section is the interval-width comparison, which "
            f"averages over all {summary['n_predictions']} predictions, and the ablation "
            f"study, where removing thermal-time alignment moves mean bias by roughly an order "
            f"of magnitude against a much smaller sampling error."
        ),
        bullet(
            "The calibration store holds 350 observations per fold built from 35 seasons "
            "re-run across 10 regimes. Those residuals are correlated within season, so "
            "effective sample size is below 350."
        ),
        bullet(
            "Vegetation-dependent results (section 6 regimes 'no vegetation', 'low valid "
            "pixel', 'radius disagreement' and both conflict regimes) rest on simulated "
            "observations and are not validated against measured NDVI."
        ),
        bullet(
            "One district, one point coordinate, 2009-2019. No claim is made about transfer "
            "to other regions, crops or sensors."
        ),
        bullet(
            "Cross-validation of a bias correction is known to be an insufficient "
            "evaluation. These results establish that the correction behaves and that the "
            "conditioning step responds to input quality; they do not establish that the "
            "correction is optimal."
        ),
    ]


def section_9() -> List[Block]:
    return [
        para(
            "Protection is sought for the method and the system as set out in sections 6 "
            "and 7. In descending order of defensibility:"
        ),
        head("9.1  Primary - method of provenance-conditioned calibration"),
        para(
            "A computer-implemented method of generating, from a predictive model whose "
            "parameters are unchanged at inference time, a prediction and an uncertainty "
            "interval, the method comprising: recording a provenance state for each input "
            "source; determining a composite provenance key from that state and from a "
            "cross-source agreement indicator; selecting a residual partition by backoff "
            "from strata keyed on that composite key; and applying the corresponding "
            "quantile, wherein the residual partitions are populated by processing "
            "held-out observations through a declared fallback chain that is the same chain "
            "by which the key is defined."
        ),
        para(
            "The claim is centred on the identity of the degradation operator and the "
            "partition key, not on partitioning alone, which is anticipated by conditional "
            "conformal prediction, nor on degrading a calibration set, which is anticipated "
            "by missing-data augmentation."
        ),
        head("9.2  Secondary - thermal-time-aligned expectation with a forecast-inclusive path"),
        para(
            "A method of forming the historical expectation against which a season-to-date "
            "anomaly is measured, comprising: accumulating thermal time over the season to "
            "date together with a forward forecast; truncating each historical season at "
            "the date on which that season reaches the same accumulated thermal time; "
            "weighting the truncated seasons by similarity of their cumulative rainfall "
            "trajectory; and discounting each forecast day by a measured skill weight that "
            "decays with lead time."
        ),
        head("9.3  Secondary - de-trended spatial support trust as a key axis"),
        para(
            "A method of deriving a confidence signal for a point-sampled vegetation index "
            "in the absence of a parcel boundary, comprising: sampling the index over a "
            "ladder of buffer radii; fitting the systematic dependence of the index on "
            "log-radius across the ladder; and taking the residual about that fit as the "
            "confidence signal, so that the signal is not dominated by the known monotone "
            "scale effect; and using the signal to form part of the partition key of "
            "9.1."
        ),
        head("9.4  Secondary - replay-sufficient hash-chained inference ledger"),
        para(
            "A computer-readable record for one inference comprising canonicalised values "
            "of every input, a digest of each retrieved source payload, the intermediate "
            "values of the computation, the selected partition and quantile, and the "
            "output, such that the output is reproducible from the record alone without "
            "re-querying any external source; and a chain in which each record commits to "
            "its predecessor, such that alteration of any stored value is detectable."
        ),
        para(
            "This is the lowest-risk subject matter of the four, being closest to a "
            "computer-readable-medium characterisation and furthest from a mathematical "
            "method. It is separated because it fails differently from 9.1 and would remain "
            "available if 9.1 were rejected.",
        ),
        head("9.5  Disclosure on excluded subject matter"),
        para(
            "Indian Patent Act section 3(k) excludes mathematical methods and computer "
            "programs per se. The subject matter here is a method operating on stored "
            "numerical data with a technical effect measurable at the level of the "
            "computation, namely reduced calibration error and reduced interval width in "
            "specified input conditions, and with exact reproducibility of a recorded "
            "result. No legal opinion is offered on whether that distinction is "
            "sufficient; it is disclosed so that the position is on the record. The "
            "alternative dispositions are set out in section 9.6."
        ),
        head("9.6  Recommended disposition"),
        bullet(
            "File 9.1 as the principal application, with 9.2, 9.3 and 9.4 as dependent "
            "claims of the same specification, and consider 9.4 as a separate filing "
            "because its risk profile differs."
        ),
        bullet(
            "Publish the method and the experimental protocol as a research paper. The "
            "validation protocol and the negative results are worth publication "
            "independently of any patent outcome."
        ),
        bullet(
            "Hold the fitted correction coefficients, the stratification thresholds and "
            "the inflation factor as a trade secret. These are the empirically tuned "
            "parameters and are the cheapest thing for a competitor to reverse-engineer "
            "from a published description, while being the least valuable to publish."
        ),
        bullet("Register copyright in the source code as a separate and unconditional form of protection."),
    ]


def section_10(summary: Dict) -> List[Block]:
    return [
        para(
            "TRL 4 is claimed. The method is formulated and implemented as working code "
            "that runs end to end, and it has been validated in the laboratory on real "
            "historical data with leave-one-season-out scoring. It has not been validated "
            "in a relevant operational environment, because no operational deployment "
            "exists, and the vegetation half of the validation rests on simulated rather "
            "than measured observations.",
        ),
        para(
            f"Evidence for the TRL 4 claim is section 8: {summary['n_predictions']} scored "
            f"predictions over {len(summary['regimes'])} degradation regimes on "
            f"{summary['n_seasons']} real crop-seasons, with a reproduction rate of "
            f"{summary['replay']['rate']:.4f} and a demonstrated reduction in calibration "
            f"error from {summary['overall']['base']['calibration_error']:.4f} to "
            f"{summary['overall']['engine']['calibration_error']:.4f}.",
        ),
        para(
            "Movement to TRL 5 would require an operational environment in which the "
            "fallback chain is exercised by real outages rather than simulation, a "
            "vegetation time series for the target farms, and a multi-district panel large "
            "enough for per-partition quantiles to be valid without backoff.",
            italic=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build(template: Path, output: Path, summary: Dict, example: Dict) -> Path:
    doc = Document(str(template))
    body = doc.element.body

    sections = [
        section_1(),
        section_2(),
        section_3(summary),
        section_4(),
        section_5(),
        section_6(),
        section_7(summary, example),
        section_8(summary),
        section_9(),
        section_10(summary),
    ]

    # Locate the ten numbered headings in document order.
    anchors: List = []
    for child in body.iterchildren():
        if child.tag.split("}")[-1] != "p":
            continue
        text = Paragraph(child, None).text.strip()
        if any(text.startswith(h) for h in HEADING_TEXTS):
            anchors.append(child)

    if len(anchors) != len(sections):
        raise SystemExit(
            f"template structure not recognised: found {len(anchors)} numbered headings, "
            f"expected {len(sections)}"
        )

    # Fill from the last heading backwards so that inserting content for an
    # earlier section cannot invalidate the anchors of a later one.
    for i in range(len(sections) - 1, -1, -1):
        start = anchors[i]
        end = anchors[i + 1] if i + 1 < len(anchors) else None
        _clear_until(body, start, end)
        new_elements = []
        for block in sections[i]:
            if block.kind == "table":
                new_elements.append(_build_table(doc, block)._element)
            else:
                new_elements.append(_build_paragraph(doc, block)._element)
        _insert_after(start, new_elements)

    _mark_trl(doc, 4)

    doc.save(str(output))
    return output


def _mark_trl(doc, level: int) -> None:
    """Tick the chosen TRL cell in the template's grid.

    The grid is a 13-row, 9-column table: row 1 holds the TRL labels, so the
    cell for a given level is row 1, column level-1. The original label is kept
    and the marker appended, so the tick is visible without destroying the
    template's own wording.
    """

    for tbl in doc.tables:
        if len(tbl.rows) != 13 or len(tbl.columns) != 9:
            continue
        cell = tbl.cell(1, level - 1)
        existing = cell.text.strip()
        if "SELECTED" not in existing:
            cell.text = f"{existing}\n(SELECTED)"
        for run in cell.paragraphs[-1].runs:
            run.bold = True
        return


def _clear_until(body, start_el, end_el) -> None:
    """Delete the template's empty placeholder paragraphs between two anchors."""

    seen = False
    for child in list(body.iterchildren()):
        if child is start_el:
            seen = True
            continue
        if child is end_el:
            break
        if not seen:
            continue
        if child.tag.split("}")[-1] != "p":
            # A real element inside the range: stop, it is not a placeholder.
            break
        if not Paragraph(child, None).text.strip():
            body.remove(child)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the IDF-B invention disclosure.")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--summary", default=str(SUMMARY_PATH))
    parser.add_argument("--out", default=str(BASE_DIR / "Invention_Disclosure_IDF-B_AgriTwin.docx"))
    args = parser.parse_args(argv)

    summary = load_summary(Path(args.summary))
    example = load_worked_example()
    out = build(Path(args.template), Path(args.out), summary, example)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
