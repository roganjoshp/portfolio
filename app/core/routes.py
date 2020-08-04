from flask import render_template

from app.core import bp


@bp.route('/')
def homepage():
    return render_template('core/homepage.html')


@bp.route('/career')
def career_homepage():
    return render_template('core/career.html')