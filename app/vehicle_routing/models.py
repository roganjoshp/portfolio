import itertools
import json
import random
import requests
import time
import uuid
import zmq

from collections import defaultdict
from flask import current_app

from app.util import jsprit_to_readable_time

import datetime as dt
import numpy as np
import pandas as pd


class RoutingProblem:
    
    def __init__(self, locations, params):
        self.locations = locations
        self.params = params
    
    def build_matrix(self):
        final_matrix = {}    # To store matrix as {(from, to): (distance, time)}
        
        # Store lat/lon as {id: (lat, lon)} to plot on frontend map
        location_map = {str(i): (location['lat'], location['lon'])
                        for i, location in enumerate(self.locations)}

        # OSRM expects lon,lat pairs :/ Start building query string
        loc_string = [','.join([str(item['lon']), str(item['lat'])])
                      for item in self.locations]
        num_locations = len(loc_string)
        
        # Add the warehouse to the matrix call string
        loc_string = ['{},{}'.format(current_app.config['WH_LON'], 
                                     current_app.config['WH_LAT'])] + loc_string
        location_map['warehouse'] = (current_app.config['WH_LAT'], 
                                     current_app.config['WH_LON'])

        # Call OSRM
        query = (current_app.config['OSRM_BASE'] 
                 + ';'.join(loc_string) + current_app.config['OSRM_END'])
        req = requests.get(query)
        matrix = req.json()
        
        # Process results into units of km and minutes
        distances = [item/1000 for sublist in matrix.get('distances')
                    for item in sublist]
        durations = [item/60 for sublist in matrix.get('durations')
                    for item in sublist]

        # Compile into the format expected by jsprit server
        location_ids = ['warehouse'] + list(map(str, range(num_locations)))
        all_location_pairs = itertools.product(location_ids, repeat=2)

        matrix_entries = []
        for i, loc_pair in enumerate(all_location_pairs):
            matrix_entries.append({'loc_from': loc_pair[0],
                                   'loc_to': loc_pair[1],
                                   'distance': str(distances[i]),
                                   'time': str(durations[i])
                                  })
            final_matrix[(loc_pair[0], loc_pair[1])] = (distances[i], 
                                                        durations[i])
        
        return matrix_entries, final_matrix, location_map
    
    def build_drivers(self):
        
        num_drivers = int(self.params['number_of_drivers'])
        get_lunch = self.params['driver_gets_break'] == 'Yes'
        drivers = []
        for x in range(int(num_drivers)):
            if get_lunch:
                lunch_start = random.randint(720, 750)
                lunch_end = lunch_start + 60
            else:
                lunch_start, lunch_end = '', ''

            drivers.append({"lunch_start": str(lunch_start),
                            "lunch_end": str(lunch_end),
                            "end_time": "1080",
                            "skills": ["default", f"driver_{x+1}"],
                            "start_time": "510",
                            "vehicle_type": "0",
                            "lunch_duration": "30" if get_lunch else "",
                            "departure_loc": "warehouse",
                            "driver_name": f"driver_{x+1}"
                        })
        vtypes = [{"type_id": "0",
                   "fixed_cost": "100",
                   "capacities": [
                       [0, 40],
                       [1, 10]
                   ],
                   "cost_per_km": "0.12",
                   "cost_per_wait": "0.17",
                   "cost_per_min": "0.17"}]

        return {'drivers': drivers, 'vtypes': vtypes}
    
    def send_to_jsprit(self, order_string, driver_config, algo_config):
        
        problem_id = uuid.uuid4().hex[:10]
        
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(current_app.config['JSPRIT_SOCKET'])

        today = dt.datetime.now().strftime('%Y_%m_%d')
        
        request = {"ordersToSolve": order_string,
                   "driverConfig": driver_config,
                   "algoParams": algo_config}
        
        dir_path = current_app.config['REQUEST_PATH']
        
        # TODO: why did we configure the the server to require no whitespace??
        with open(f'{dir_path}/{today}_{problem_id}.txt', 'w') as outfile:
            output_json = json.dumps(request)
            outfile.write(output_json.replace(' ',''))
        
        socket.send_string(f'{dir_path}/{today}_{problem_id}.txt')
        response = socket.recv()
        
        socket.close()
        return json.loads(response)
    
    def solve_route(self):
        jsprit_data = {}

        # First get the distance/time matrix
        matrix, my_matrix, location_dict = self.build_matrix()
        jsprit_data['matrix'] = matrix
        
        # Now configure the vehicles and vehicle types
        driver_config = self.build_drivers()
        
        # Finally, add the orders all as deliveries
        jsprit_data['pickups'] = {}
        jsprit_data['shipments'] = {}

        locations = self.locations
        customer_names = {}
        timeslots = {}
        deliveries = {}
        for i, job in enumerate(locations):
            timeslots[str(i)] = {'start': job['start'], 'end': job['end']}
            deliveries[str(i)] = {'r_id': str(i),
                                  'r_tw_from': str(job['jsprit_start']),
                                  'r_tw_to': str(job['jsprit_end']),
                                  'dname_skill': 'default',
                                  'service_time': "5"}
        jsprit_data['deliveries'] = deliveries

        algo_config = {'numberOfIterations': '100', 
                       'isInfinite': 'false'}

        send_time = time.time()
        result = self.send_to_jsprit(jsprit_data, driver_config, algo_config)
        solve_time = time.time() - send_time
        routes, stats = self.process_results(result, my_matrix, location_dict)
        return routes, stats
        
    def process_results(self, result, matrix, location_coords):
        
        location_dict = {i: location for 
                         i, location in enumerate(self.locations)}
        
        raw_routes = result['routes']
        driver_routes = {}
        all_stats = defaultdict(dict)
        
        for driver_name, route in raw_routes.items():
            previous_location = 'warehouse' # Init at the starting location
            driver_number = int(driver_name.split('_')[1])
            individual_route = []
            route_stats = {}
            for i, job in enumerate(route):
                
                details = {'job_id': i,
                           'location': '',
                           'departure_time': '',
                           'arrival_time': '',
                           'activity': '',
                           'customer_name': '',
                           'slot_start': '',
                           'slot_end': '',
                           'waiting_time': '',
                           'lat': '',
                           'lon': ''}
                
                if i == 0:
                    # Leaving the warehouse
                    details['location'] = 'Warehouse'
                    details['departure_time'] = jsprit_to_readable_time(
                                                           job['num_departure']
                                                           )
                    details['activity'] = 'Depart'
                    details['customer_name'] = 'Depot'
                    details['lat'] = location_coords['warehouse'][0]
                    details['lon'] = location_coords['warehouse'][1]
                    
                elif i == (len(route) - 1):
                    # Arriving back at the warehouse
                    details['location'] = 'Warehouse'
                    details['arrival_time'] = jsprit_to_readable_time(
                                       float(job['arrival'].split(':')[0]) / 60
                                       )
                    details['activity'] = 'Arrive'
                    details['customer_name'] = 'Depot'
                    details['lat'] = location_coords['warehouse'][0]
                    details['lon'] = location_coords['warehouse'][1]
                    
                elif job['tracking'] == 'lunch':
                    details['activity'] = 'Lunch'
                    details['customer_name'] = ''
                    details['arrival_time'] = jsprit_to_readable_time(
                                                      job['num_departure'] - 30
                                                      )
                    details['departure_time'] = jsprit_to_readable_time(
                                                          job['num_departure']
                                                          )
                    all_stats[driver_number]['had_lunch'] = True
                else:
                    # We have a flat 5 minutes for service time
                    tracking = int(job['tracking'])
                    waiting_time = int(float(job['num_departure']) - 5
                                        - float(job['num_arrival']))
                    
                    first_name, surname = (location_dict[tracking]['name']
                                                                  .split(' '))
                    
                    first_name = first_name[0] + '.'
                    name = first_name + ' ' + surname
                    details['location'] = name
                    details['customer_name'] = name
                    details['departure_time'] = jsprit_to_readable_time(
                                                           job['num_departure']
                                                           )
                    details['arrival_time'] = jsprit_to_readable_time(
                                                float(job['num_departure']) - 5
                                                )
                    details['waiting_time'] = waiting_time
                    details['activity'] = 'Delivery'
                    details['slot_start'] = location_dict[tracking]['start']
                    details['slot_end'] = location_dict[tracking]['end']
                    details['lat'] = location_coords[job['tracking']][0]
                    details['lon'] = location_coords[job['tracking']][1]
                    
                    # Grab some stats
                    travel_distance, travel_time = matrix[(previous_location,
                                                           job['tracking'])]
                    
                    all_stats[driver_number]['distance'] = (
                                    all_stats[driver_number].get('distance', 0) 
                                    + travel_distance)
                    all_stats[driver_number]['time'] = (
                                    all_stats[driver_number].get('time', 0) 
                                    + travel_time)
                    all_stats[driver_number]['waiting'] = (
                                    all_stats[driver_number].get('waiting', 0) 
                                    + waiting_time)
                    previous_location = job['tracking']
                    
                individual_route.append(details)
            all_stats[driver_number]['had_lunch'] = (
                                all_stats[driver_number].get('had_lunch', False)
                                )
            all_stats[driver_number]['num_jobs'] = i - 1
            driver_routes[driver_number] = individual_route
        
        # Clean up the stats
        for driver_id, stat_dict in all_stats.items():
            for stat_name, value in stat_dict.items():
                if not isinstance(value, bool):
                    all_stats[driver_id][stat_name] = round(float(value), 1)
        
        # Add any missing driver routes so we can show an empty table
        for driver_number in current_app.config['NUM_DRIVERS']:
            if not driver_routes.get(driver_number):
                driver_routes[driver_number] = []
        
        return driver_routes, all_stats
        
    @staticmethod
    def validate_problem(req):
        
        valid_num_customers = current_app.config['NUM_CUSTOMERS']
        valid_slot_lengths = current_app.config['TIME_SLOTS']
        valid_num_drivers = current_app.config['NUM_DRIVERS']
        valid_break_options = current_app.config['DRIVER_BREAKS']
        
        try:
            num_customers = int(req['number_of_customers'])
            if num_customers not in valid_num_customers:
                return False
            
            slot_length = int(req['delivery_slot_length'])
            if slot_length not in valid_slot_lengths:
                return False
            
            num_drivers = int(req['number_of_drivers'])
            if num_drivers not in valid_num_drivers:
                return False
            
            if req['driver_gets_break'] not in valid_break_options:
                return False
            
        except Exception:
            return False
        
        return True
    
    @staticmethod
    def build_locations(req):
        
        samples = int(req['number_of_customers'])
        lats = np.random.uniform(current_app.config['MIN_LAT'], 
                                 current_app.config['MAX_LAT'], 
                                 samples).round(6).tolist()
        lons = np.random.uniform(current_app.config['MIN_LON'], 
                                 current_app.config['MAX_LON'], 
                                 samples).round(6).tolist()
        names = np.random.choice(current_app.config['CUSTOMER_NAMES'],
                                 samples,
                                 replace=False).tolist()
        jsprit_starts = np.random.choice(current_app.config['START_TIMES'],
                                         samples, 
                                         replace=True)
        jsprit_ends = jsprit_starts + 60 * int(req['delivery_slot_length'])
        starts = list(map(jsprit_to_readable_time, jsprit_starts.tolist()))
        ends = list(map(jsprit_to_readable_time, jsprit_ends.tolist()))
        
        # We also want to be able to display the name and timeslot on markers
        details = [f'{name}\n{starts[i]}-{ends[i]}' 
                   for i, name in enumerate(names)]
        
        joined = zip(lats, lons, names, starts, ends, jsprit_starts.tolist(), 
                     jsprit_ends.tolist(), details)
        keys = ['lat', 'lon', 'name', 'start', 'end', 'jsprit_start', 
                'jsprit_end', 'details']
        
        return [dict(zip(keys, item)) for item in joined]
        
        