"""Durations from recorded stage exits only; no synthetic lifecycle dates."""

from collections import defaultdict
from statistics import median
from performance_metrics import timestamp


def summarize(connection, cases, start, end, now):
    events = defaultdict(list)
    transitions = 0
    ids = {case["id"] for case in cases}
    for row in connection.execute(
        "SELECT case_id,stage,outcome,created FROM history ORDER BY case_id,id"
    ):
        if row["case_id"] not in ids:
            continue
        date = timestamp(row["created"])
        events[row["case_id"]].append((row["stage"], row["outcome"], date))
        if date and start <= date < end and date <= now:
            transitions += 1
    samples = defaultdict(list)
    for case in cases:
        created = timestamp(case["created"])
        previous_stage, previous_date = None, None
        sequence = events[case["id"]]

        def completion(index):
            return (index == len(sequence) - 1 and case["stage"] == 3) or (
                index + 1 < len(sequence) and sequence[index + 1][:2] == (3, "Reopened")
            )

        for index, (stage, outcome, date) in enumerate(sequence):
            if outcome == "Reopened":
                previous_stage, previous_date = None, None
                continue
            if (
                not date
                or date > now
                or outcome not in ("Done", "Deferred", "No applicable work")
            ):
                previous_stage, previous_date = None, None
                continue
            if start <= date < end:
                if stage == 0 and created and created <= date:
                    samples["waiting"].append((date - created).total_seconds() / 86400)
                if (
                    (stage == 1 or stage == 2 and completion(index))
                    and previous_stage == stage - 1
                    and previous_date
                    and previous_date <= date
                ):
                    samples["analysis" if stage == 1 else "packaging"].append(
                        (date - previous_date).total_seconds() / 86400
                    )
            previous_stage, previous_date = stage, date
        # Never infer end-to-end analysis duration from creation or import time.
        chain = {}
        for index, (stage, outcome, date) in enumerate(sequence):
            if (
                outcome not in ("Done", "Deferred", "No applicable work")
                or not date
                or date > now
            ):
                chain = {}
                continue
            if stage == 0:
                chain = {0: date}
            elif stage == 1 and 0 in chain and date >= chain[0]:
                chain[1] = date
            elif stage == 2:
                if (
                    completion(index)
                    and 1 in chain
                    and date >= chain[1]
                    and start <= date < end
                ):
                    samples["analysis_to_completion"].append(
                        (date - chain[0]).total_seconds() / 86400
                    )
                chain = {}
            else:
                chain = {}
    return {
        "transitions": transitions,
        "durations": {
            key: {
                "median": median(samples[key]) if samples[key] else None,
                "records": len(samples[key]),
            }
            for key in ("waiting", "analysis", "packaging", "analysis_to_completion")
        },
    }
