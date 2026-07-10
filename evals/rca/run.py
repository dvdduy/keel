from __future__ import annotations

import sys

from keel.application.agent.diagnose import diagnose

from evals.rca.cases import cases
from evals.rca.score import EvalReport, aggregate, score_case


MIN_TOP1_ACCURACY = 0.80
MAX_FALSE_POSITIVE_RATE = 0.10


def main() -> int:
    results = tuple(score_case(case, diagnose(case.dossier)) for case in cases())
    report = aggregate(results)
    print(_format_report(report))

    if (
        report.top1_accuracy < MIN_TOP1_ACCURACY
        or report.false_positive_rate > MAX_FALSE_POSITIVE_RATE
    ):
        return 1
    return 0


def _format_report(report: EvalReport) -> str:
    return "\n".join(
        (
            "RCA eval report",
            f"cases: {report.n}",
            f"top1_accuracy: {report.top1_accuracy:.2f}",
            f"top3_accuracy: {report.top3_accuracy:.2f}",
            f"false_positive_rate: {report.false_positive_rate:.2f}",
            f"abstention_rate: {report.abstention_rate:.2f}",
        )
    )


if __name__ == "__main__":
    sys.exit(main())
