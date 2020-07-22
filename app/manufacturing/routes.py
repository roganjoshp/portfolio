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
    ptv_status = Machines.get_current_status()
    return render_template('manufacturing/homepage.html',
                           ptv_status=ptv_status)
    

@bp.route('/get_ptv_update', methods=['POST'])
def get_ptv_update():
    ptv_status = Machines.get_current_status()
    return render_template('manufacturing/ptv_screen.html',
                           ptv_status=ptv_status)