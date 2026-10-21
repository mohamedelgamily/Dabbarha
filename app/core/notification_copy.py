"""Versioned, privacy-aware bilingual push copy. Facts come only from stored rows."""
from decimal import Decimal


COPY_VERSION = "v1"
ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _amount(value: Decimal) -> str:
    return f"{value:,.2f}"


def render_copy(kind: str, language: str, privacy: str, *, item_name: str, amount: Decimal, days: int = 0):
    if language == "ar":
        if kind == "payment_completed":
            return ("اتسجلت دفعتك ✅", "تم تأكيد تسجيلك إن القسط اتدفع." if privacy == "private" else
                    f"تم تسجيل إن قسط {item_name} بقيمة {_amount(amount)} اتدفع.")
        if kind == "due_today":
            return ("قسطك معاده النهارده! 👀", "عندك دفعة مستحقة النهارده. دبّرها براحتك." if privacy == "private" else
                    f"قسط {item_name} بقيمة {_amount(amount)} مستحق النهارده.")
        if kind == "overdue":
            return ("تذكير سريع 👀", "في دفعة فات ميعادها ولسه متسجلتش كمدفوعة." if privacy == "private" else
                    f"قسط {item_name} بقيمة {_amount(amount)} فات ميعاده ولسه مش متسجل كمدفوع.")
        number = str(max(days, 1)).translate(ARABIC_DIGITS)
        return (f"فاضل {number} يوم على قسطك! 👀", "دفعة جاية قرب ميعادها. دبّرها من بدري وخلي بالك مرتاح!" if privacy == "private" else
                f"قسط {item_name} بقيمة {_amount(amount)} قرب معاده. دبّرها من بدري وخلي بالك مرتاح!")
    if kind == "payment_completed":
        return ("Payment marked paid ✅", "You marked this payment as paid." if privacy == "private" else
                f"You marked {item_name} ({_amount(amount)}) as paid.")
    if kind == "due_today":
        return ("Payment due today 👀", "You have a payment due today. Take a look when you can." if privacy == "private" else
                f"Your {item_name} payment ({_amount(amount)}) is due today.")
    if kind == "overdue":
        return ("A quick payment reminder 👀", "A payment is past due and isn't marked paid yet." if privacy == "private" else
                f"Your {item_name} payment ({_amount(amount)}) is past due and isn't marked paid yet.")
    return ("A little heads-up! 👀", f"A payment is coming up in {max(days, 1)} days. Stay one step ahead!" if privacy == "private" else
            f"Your {item_name} payment ({_amount(amount)}) is coming up in {max(days, 1)} days. Stay one step ahead!")
