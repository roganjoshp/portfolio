from flask import request, render_template, current_app

from app import scheduler
from app.manufacturing import bp
from app.manufacturing.models import Machines, MachineHistory, Problem, Solver


@scheduler.task('interval', id='update_silos', seconds=3)
def update_machine_status():
    with scheduler.app.app_context():
        machines = Machines.query.all()
        for machine in machines:
            machine.update_status()


@bp.route('/homepage', methods=['GET'])
def homepage():
    ptv_status = Machines.get_current_status()
    plot = MachineHistory.get_plots('product_count')
    shifts = [item for item in current_app.config['SHIFT_HOURS']
              if item != 'null']
    machines = current_app.config['MACHINE_NAMES']
    products = current_app.config['PRODUCT_NAMES']
    forecast = Problem.create_forecast()
    return render_template('manufacturing/homepage.html',
                           ptv_status=ptv_status,
                           plot=plot,
                           shifts=shifts,
                           products=products,
                           machines=machines,
                           forecast=forecast)
    

@bp.route('/get_ptv_update', methods=['POST'])
def get_ptv_update():
    ptv_status = Machines.get_current_status()
    
    return render_template('manufacturing/ptv_screen.html',
                           ptv_status=ptv_status)
    
    
@bp.route('/plot_historical_data', methods=['POST'])
def plot_historical_data():
    req = request.json
    stat = req.get('stat')
    plot = MachineHistory.get_plots(stat)
    return render_template('manufacturing/machine_history_graphs.html',
                           plot=plot)
    
    
@bp.route('/create_problem', methods=['POST'])
def create_problem():
    problem = Problem(request.form)
    is_valid = problem.parse_request()
    if is_valid:
        problem.finalise_build()
        solver = Solver(problem)
        solver.run_solver()
        solution = solver.get_solution()
        return render_template(
                    'manufacturing/results_graphs.html',
                    num_panels=int(len(solution['productivity_graphs']) / 2),
                    solution=solution
                    )
    return False