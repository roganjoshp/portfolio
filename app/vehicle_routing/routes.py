from flask import current_app, jsonify, render_template, request, session

from app.vehicle_routing import bp
from app.vehicle_routing.models import RoutingProblem

import time

import numpy as np


@bp.route('/')
def homepage():
    customer_numbers = current_app.config['NUM_CUSTOMERS']
    driver_numbers = current_app.config['NUM_DRIVERS']
    slot_lengths = current_app.config['TIME_SLOTS']
    driver_gets_break = current_app.config['DRIVER_BREAKS']
    return render_template('vehicle_routing/homepage.html',
                           customer_numbers=customer_numbers,
                           driver_numbers=driver_numbers,
                           slot_lengths=slot_lengths,
                           driver_break_options=driver_gets_break)
    
    
@bp.route('/create_problem', methods=['POST'])
def create_problem():
    req = request.form.to_dict()
    is_valid = RoutingProblem.validate_problem(req)
    
    if is_valid:
        locations = RoutingProblem.build_locations(req)
    else:
        locations = []
    
    session['routing_locations'] = locations
    del req['csrf_token']
    session['routing_params'] = req
    
    return jsonify({'is_valid': is_valid,
                    'locations': locations})
    

@bp.route('/solve_problem', methods=['POST'])
def solve_problem():
    
    locations = session['routing_locations']
    params = session['routing_params']
    
    routes = {}
    stats = {}
    if locations:
        solver = RoutingProblem(locations, params)
        routes, stats = solver.solve_route()
    import json
    num_drivers = current_app.config['NUM_DRIVERS']
    print(stats)
    return render_template('vehicle_routing/results_panel.html',
                           num_drivers=num_drivers,
                           routes=routes, 
                           stats=stats)