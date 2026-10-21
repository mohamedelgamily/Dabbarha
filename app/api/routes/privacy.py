from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_ACCOUNT_DELETION_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="index,follow">
  <title>Dabbarha — Account deletion</title>
  <style>
    :root { color-scheme: light; font: 16px/1.6 system-ui, sans-serif; color: #18312d; background: #f5f8f6; }
    body { max-width: 760px; margin: 0 auto; padding: 2rem 1.1rem; }
    main { background: white; border: 1px solid #dce8e2; border-radius: 1rem; padding: clamp(1.2rem, 4vw, 2.5rem); }
    h1, h2 { line-height: 1.25; color: #145b4a; }
    section + section { border-top: 1px solid #e5ede9; margin-top: 2rem; padding-top: 1rem; }
    .notice { background: #eef7f2; border-radius: .65rem; padding: 1rem; }
    a { color: #126b56; }
  </style>
</head>
<body>
<main>
  <h1>Delete your Dabbarha account</h1>
  <p>You can permanently delete your account from Profile or Settings in the app. We ask you to enter your password and confirm the deletion. If you cannot sign in, once the publisher has posted a support contact on the official app listing, use it to request deletion. The publisher should verify that you own the account before acting. Never send your password to support. This information page does not itself receive or process requests.</p>
  <h2>What deletion removes</h2>
  <p>After confirmation, Dabbarha permanently deletes your profile and financial settings, obligations and installment schedules, payment-status history, notification history and preferences, registered push-device tokens, login sessions and legacy conversation data. Deletion is immediate after the request is accepted and cannot be undone.</p>
  <p class="notice">The approved policy limits encrypted-backup retention to 30 days; the publisher must have this control active before using this notice. A backup created before deletion may contain the account until it expires. Restores must follow the deletion-reconciliation procedure and must not be returned to service directly from an old snapshot.</p>
  <section lang="ar" dir="rtl">
    <h1>حذف حساب دبّرها</h1>
    <p>تقدر تحذف حسابك نهائيًا من الملف الشخصي أو الإعدادات في التطبيق. هنطلب منك كلمة المرور وتأكيد الحذف. لو مش قادر تسجّل دخول، بعد ما الناشر يضيف وسيلة تواصل لصفحة التطبيق الرسمية، استخدمها لطلب حذف الحساب. المفروض الناشر يتأكد الأول إن الحساب يخصك. ما تبعتش كلمة المرور للدعم. الصفحة دي للمعلومات ومابتستقبلش الطلبات أو تنفذها.</p>
    <h2>إيه البيانات اللي هتتحذف؟</h2>
    <p>بعد التأكيد، هنحذف نهائيًا بيانات الملف الشخصي والإعدادات المالية، والالتزامات وجداول الأقساط، وسجل حالات الدفع، وسجل وإعدادات التنبيهات، ورموز أجهزة الإشعارات، وجلسات تسجيل الدخول والمحادثات القديمة. الحذف بيتم فور قبول الطلب ومش ممكن التراجع عنه.</p>
    <p class="notice">السياسة المعتمدة بتحدد الاحتفاظ بالنسخ الاحتياطية المشفّرة بحد أقصى ٣٠ يومًا؛ لازم الناشر يفعّل الإجراء ده قبل استخدام الإفصاح. ممكن نسخة اتعملت قبل الحذف تفضل محتوية على الحساب لحد انتهاء مدتها. لازم أي استعادة تتبع إجراء مراجعة الحذف الموثّق، وماينفعش تشغيل نسخة قديمة مباشرة.</p>
  </section>
</main>
</body>
</html>"""


@router.get("/privacy/account-deletion", response_class=HTMLResponse,
            include_in_schema=False, summary="Public account-deletion information")
def account_deletion_information() -> HTMLResponse:
    return HTMLResponse(_ACCOUNT_DELETION_PAGE, headers={"Cache-Control": "public, max-age=300"})
