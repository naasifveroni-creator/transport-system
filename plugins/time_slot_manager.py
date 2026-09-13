from models import db, GlobalTimeSlot, CampaignTimeSlot


class TimeSlotManager:
    def __init__(self, db_path=None):
        # db_path kept for backwards compatibility; unused now.
        pass

    def get_global_settings(self):
        rows = GlobalTimeSlot.query.order_by(GlobalTimeSlot.slot).all()
        return [{"slot": r.slot, "enabled": bool(r.enabled)} for r in rows]

    def set_global_slot(self, slot, enabled=True):
        existing = GlobalTimeSlot.query.filter_by(slot=slot).first()
        if existing:
            existing.enabled = bool(enabled)
        else:
            db.session.add(GlobalTimeSlot(slot=slot, enabled=bool(enabled)))
        db.session.commit()

    def get_campaign_slots(self):
        rows = CampaignTimeSlot.query.order_by(
            CampaignTimeSlot.campaign, CampaignTimeSlot.slot
        ).all()
        return [
            {"campaign": r.campaign, "slot": r.slot, "enabled": bool(r.enabled)}
            for r in rows
        ]

    def set_campaign_slot(self, campaign, slot, enabled=True):
        existing = CampaignTimeSlot.query.filter_by(
            campaign=campaign, slot=slot
        ).first()
        if existing:
            existing.enabled = bool(enabled)
        else:
            db.session.add(CampaignTimeSlot(
                campaign=campaign, slot=slot, enabled=bool(enabled)
            ))
        db.session.commit()
