from flask import render_template, flash, redirect, url_for

from app import db
from app.core import bp
from app.core.forms import ContactForm
from app.core.models import Messages


@bp.route('/')
def homepage():
    return render_template('core/homepage.html')


@bp.route('/career')
def career_homepage():
    return render_template('core/career.html')


@bp.route('/about')
def about_homepage():
    return render_template('core/about_site.html')


@bp.route('/contact', methods=['POST', 'GET'])
def contact_homepage():
    form = ContactForm()
    if form.validate_on_submit():
        message = Messages(name=form.name.data,
                           email=form.email.data,
                           phone=form.phone.data,
                           message=form.message.data)
        db.session.add(message)
        db.session.commit()
        flash("Thank you for your message! I will respond as soon as possible.")
        return redirect(url_for('core.contact_homepage'))
    
    return render_template('core/contact.html',
                           form=form)