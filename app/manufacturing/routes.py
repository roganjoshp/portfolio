from flask import render_template, current_app

from app import scheduler
from app.manufacturing import bp
from app.manufacturing.models import Machines


@scheduler.task('interval', id='update_silos', seconds=3)
def update_machine_status():
    with scheduler.app.app_context():
        machines = Machines.query.all()
        for machine in machines:
            machine.update_status()


@bp.route('/homepage', methods=['GET'])
def homepage():
    current_status = Machines.get_status()
    return render_template('manufacturing/homepage.html')