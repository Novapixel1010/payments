# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE
import json

import frappe
from frappe import _, Redirect
from frappe.utils import cint, fmt_money

from payments.payment_gateways.doctype.stripe_settings.stripe_settings import (
    get_gateway_controller,
)

no_cache = 1

EXPECTED_KEYS = (
    "amount",
    "title",
    "description",
    "reference_doctype",
    "reference_docname",
    "payer_name",
    "payer_email",
    "currency",
    "payment_gateway",
)


def get_context(context):
    context.no_cache = 1

    missing = set(EXPECTED_KEYS) - set(frappe.form_dict.keys())
    if missing:
        title = _("Expected keys: {0}. Received keys: {1}").format(
            EXPECTED_KEYS, list(frappe.form_dict.keys())
        )
        frappe.log_error(_("Missing keys in form_dict"), title)
        frappe.redirect_to_message(
            _("Some information is missing"),
            _("Looks like someone sent you to an incomplete URL. Please ask them to look into it."),
        )
        frappe.local.flags.redirect_location = frappe.local.response.location
        raise Redirect

    # all keys present
    for key in EXPECTED_KEYS:
        context[key] = frappe.form_dict[key]

    controller = get_gateway_controller(
        context.reference_doctype, context.reference_docname, context.payment_gateway
    )
    context.publishable_key = get_api_key(controller)
    context.image = get_header_image(controller)

    context.amount = fmt_money(context.amount, context.currency)

    if is_subscription(context.reference_doctype, context.reference_docname):
        plan = frappe.db.get_value(
            context.reference_doctype, context.reference_docname, "payment_plan"
        )
        recurrence = frappe.db.get_value("Payment Plan", plan, "recurrence")
        context.amount = f"{context.amount} {_('{0}').format(recurrence)}"


def get_api_key(gateway_controller):
    key = frappe.db.get_value("Stripe Settings", gateway_controller, "publishable_key")
    if cint(frappe.form_dict.get("use_sandbox")):
        key = frappe.conf.get("sandbox_publishable_key") or key
    return key


def get_header_image(gateway_controller):
    return frappe.db.get_value("Stripe Settings", gateway_controller, "header_img")


@frappe.whitelist(allow_guest=True)
def make_payment(stripe_token_id, data, reference_doctype=None, reference_docname=None, payment_gateway=None):
    try:
        payload = json.loads(data)
    except ValueError:
        frappe.throw(_("Invalid payment data"), frappe.ValidationError)

    payload["stripe_token_id"] = stripe_token_id
    controller = get_gateway_controller(reference_doctype, reference_docname, payment_gateway)

    if is_subscription(reference_doctype, reference_docname):
        ref = frappe.get_doc(reference_doctype, reference_docname)
        result = ref.create_subscription("stripe", controller, payload)
    else:
        settings = frappe.get_doc("Stripe Settings", controller)
        result = settings.create_request(payload)

    frappe.db.commit()
    return result


def is_subscription(reference_doctype, reference_docname):
    meta = frappe.get_meta(reference_doctype)
    if not meta.has_field("is_a_subscription"):
        return False
    return bool(frappe.db.get_value(reference_doctype, reference_docname, "is_a_subscription"))
