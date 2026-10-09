"""Blind review: Reviewers see "Candidate 12" instead of the person's name."""
import copy


def mask_candidate(row: dict, title: str) -> dict:
    if title != "Reviewer":
        return row
    return {**row, "name": f"Candidate {row['id']}"}


def mask_record(rec: dict, title: str) -> dict:
    if title != "Reviewer":
        return rec
    rec = copy.deepcopy(rec)
    rec["summary"]["candidate"] = f"Candidate {rec['candidate_id']}"
    return rec
