from datetime import datetime
from tz_util import now_local, now_iso


class BillingMIS:
    def __init__(self):
        # In-memory invoice store
        self.invoices = []

    def create_invoice(self, user_id, amount, description=""):
        invoice = {
            "id": len(self.invoices) + 1,
            "user_id": user_id,
            "amount": float(amount),
            "description": description,
            "status": "pending",
            "created_at": now_iso()
        }
        self.invoices.append(invoice)
        return invoice

    def mark_paid(self, invoice_id):
        for inv in self.invoices:
            if inv["id"] == invoice_id:
                inv["status"] = "paid"
                inv["paid_at"] = now_iso()
                return True
        return False

    def get_overview(self):
        total_revenue = sum(i["amount"] for i in self.invoices if i["status"] == "paid")
        pending = [i for i in self.invoices if i["status"] == "pending"]
        paid = [i for i in self.invoices if i["status"] == "paid"]
        return {
            "total_revenue": total_revenue,
            "pending_invoices": len(pending),
            "paid_invoices": len(paid),
            "pending_amount": sum(i["amount"] for i in pending),
            "revenue_trend": 0,
            "completion_rate": (len(paid) / len(self.invoices) * 100) if self.invoices else 0
        }

    def list_invoices(self):
        return list(self.invoices)
