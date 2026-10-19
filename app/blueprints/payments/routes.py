from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.blueprints.payments import bp
from app.blueprints.rbac import roles_required
from app.extensions import db
from app.models import PromoCode, Certificate
from app.services.audit_service import log_action
from app.constants import ROLE_SUPERADMIN, ROLE_ACCOUNTANT, ROLE_LOCATION_ADMIN
from app.forms.quest_forms import PromoCodeForm, CertificateForm


@bp.route("/promocodes")
@login_required
@roles_required(ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN)
def promocodes():
    items = PromoCode.query.order_by(PromoCode.id.desc()).all()
    return render_template("payments/promocodes.html", items=items)


@bp.route("/promocodes/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN)
def promocode_new():
    form = PromoCodeForm()
    if form.validate_on_submit():
        code = form.code.data.strip().upper()
        if PromoCode.query.filter_by(code=code).first():
            flash("Промокод с таким кодом уже существует", "danger")
            return render_template("payments/promocode_form.html", form=form)
        promo = PromoCode(
            code=code,
            discount_percent=form.discount_percent.data or 0,
            discount_amount=form.discount_amount.data or 0,
            valid_from=form.valid_from.data,
            valid_to=form.valid_to.data,
            usage_limit=form.usage_limit.data or 0,
        )
        db.session.add(promo)
        db.session.flush()
        log_action("promocode_created", "PromoCode", promo.id, f"code={promo.code}")
        db.session.commit()
        flash("Промокод создан", "success")
        return redirect(url_for("payments.promocodes"))
    return render_template("payments/promocode_form.html", form=form)


@bp.route("/certificates")
@login_required
@roles_required(ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN, ROLE_ACCOUNTANT)
def certificates():
    items = Certificate.query.order_by(Certificate.id.desc()).all()
    return render_template("payments/certificates.html", items=items)


@bp.route("/certificates/new", methods=["GET", "POST"])
@login_required
@roles_required(ROLE_SUPERADMIN, ROLE_LOCATION_ADMIN)
def certificate_new():
    form = CertificateForm()
    if form.validate_on_submit():
        code = form.code.data.strip().upper()
        if Certificate.query.filter_by(code=code).first():
            flash("Сертификат с таким кодом уже существует", "danger")
            return render_template("payments/certificate_form.html", form=form)
        cert = Certificate(
            code=code,
            initial_balance=form.initial_balance.data,
            balance=form.initial_balance.data,
            expires_at=form.expires_at.data,
            issued_to_name=form.issued_to_name.data,
        )
        db.session.add(cert)
        db.session.flush()
        log_action("certificate_created", "Certificate", cert.id, f"code={cert.code} nominal={cert.initial_balance}")
        db.session.commit()
        flash("Сертификат создан", "success")
        return redirect(url_for("payments.certificates"))
    return render_template("payments/certificate_form.html", form=form)
