from flask import render_template

from app.core import bp


@bp.route('/')
def homepage():
    return render_template('core/homepage.html')