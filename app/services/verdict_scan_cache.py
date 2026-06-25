import json

from sqlalchemy.orm import Session

from app.models import AISummary


SCAN_SUMMARY_TYPE = "verdict-scan"


def _scan_payload(sig_dict: dict) -> dict:
    return {
        "action": sig_dict.get("action", "needs-data"),
        "label": sig_dict.get("label", "Needs Data"),
        "confidence": sig_dict.get("confidence", 0),
        "generated_at": sig_dict.get("generated_at", ""),
    }


def _latest_scan_payload(db: Session, ticker: str) -> dict | None:
    row = (
        db.query(AISummary)
        .filter(AISummary.ticker == ticker, AISummary.summary_type == SCAN_SUMMARY_TYPE)
        .order_by(AISummary.generated_at.desc())
        .first()
    )
    if not row:
        return None
    try:
        payload = json.loads(getattr(row, "summary_text", "") or "{}")
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def attach_since_last_scan(db: Session, ticker: str, sig_dict: dict) -> bool:
    current = _scan_payload(sig_dict)
    previous = _latest_scan_payload(db, ticker)
    sig_dict["since_last_scan"] = None
    should_store = previous is None

    if previous:
        prev_action = previous.get("action")
        curr_action = current["action"]
        prev_conf = previous.get("confidence")
        curr_conf = current["confidence"]
        if prev_action != curr_action:
            sig_dict["since_last_scan"] = {"label": f"was {previous.get('label', prev_action)}"}
            should_store = True
        elif isinstance(prev_conf, int) and isinstance(curr_conf, int):
            delta = curr_conf - prev_conf
            if delta:
                sig_dict["since_last_scan"] = {"label": f"conf {delta:+d}"}
                should_store = True
            else:
                sig_dict["since_last_scan"] = {"label": "same verdict"}

    if should_store:
        db.add(AISummary(
            ticker=ticker,
            summary_type=SCAN_SUMMARY_TYPE,
            summary_text=json.dumps(current),
            price_when_generated=None,
            model_used="deterministic",
        ))
    return should_store
