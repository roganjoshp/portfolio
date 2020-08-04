import random
import sqlite3

from copy import deepcopy
from flask import current_app
from itertools import groupby
from math import exp
from operator import itemgetter
from sqlalchemy import and_
from sqlalchemy.sql import func

from app import db
from app.util import chunk

import datetime as dt
import numpy as np
import pandas as pd


class MachineStats(db.Model):
    """ General stats about machines to create a fake history

    In order to generate fake machine data, it's necessary to know the ideal
    run rate in addition to some fake parameters to estimate the likelihood that
    the machine will suffer a fault

    :param ideal_run_rate:       product count/minute if there are no faults
    :param efficiency:           General efficiency when running without fault
    :param min_downtime_secs:    The minimum duration of a downtime event to 
                                 reflect the difficulty of restarting a machine
    :param downtime_probability: The percentage likelihood of a downtime per 
                                 update cycle
    :param restart_probability:  The percentage likelihood of recovering 
                                 production after being down for 
                                 min_downtime_secs
    """
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer,
                           db.ForeignKey('machines.id',
                                         ondelete='CASCADE'),
                           index=True)
    machine = db.relationship('Machines', backref=db.backref('stats',
                                                             uselist=False))
    ideal_run_rate = db.Column(db.Integer)
    efficiency = db.Column(db.Float)
    min_downtime_secs = db.Column(db.Integer)
    downtime_probability = db.Column(db.Float)
    restart_probability = db.Column(db.Float)


class MachineHistory(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer,
                           db.ForeignKey('machines.id',
                                         ondelete='CASCADE'),
                           index=True)
    machine = db.relationship('Machines', backref='history')
    datetime = db.Column(db.DateTime, index=True)
    product_count = db.Column(db.Integer)
    down_count = db.Column(db.Integer)
    down_secs = db.Column(db.Integer)
    
    @staticmethod
    def get_plots(stat):
        
        allowed_stats = ('product_count', 'down_count', 'down_secs', 'oee')
        if stat not in allowed_stats:
            # Assume injection attempt and abort
            return {}
        
        rtn = {}
        
        if stat != 'oee':
            stat_name = stat
        else:
            # We need to scale this to ideal runrate
            stat_name = 'product_count'
        
        # Pass query off to raw, to avoid ORM overhead. No need for it here
        data = db.session.execute(
                      f"""
                       SELECT machines.name AS name, 
                              machine_history.datetime,
                              machine_history.{stat_name} 
                       FROM machine_history
                       JOIN machines ON machines.id = machine_history.machine_id
                       ORDER BY name, machine_history.datetime
                       """
                       ).fetchall()
            
        df = pd.DataFrame(data, columns=['name', 'datetime', 'value'])
        
        if stat == 'oee':
            ideal_run_rates = db.session.execute(
                         """
                         SELECT machines.name AS name,
                                machine_stats.ideal_run_rate
                         FROM machine_stats
                         JOIN machines ON machines.id = machine_stats.machine_id
                         """
                         ).fetchall()
            
            mapper = {name: run_rate * 60 for name, run_rate in ideal_run_rates}
            df['value'] = df.apply(lambda x: x['value'] / mapper.get(x['name']),
                                   axis=1)
            df['value'] *= 100
        
        max_val = 0
        
        # Make JSON serializable
        for name, data in df.groupby('name'):
            rtn[name] = {'datetimes': data['datetime'].tolist(),
                         'plot_values': data['value'].astype(int).tolist()}
            if data['value'].max() > max_val:
                max_val = data['value'].max()
        
        stat_map = {'product_count': {'title': 'Product Count',
                                      'x_axis': 'Datetime',
                                      'y_axis': 'Items Produced'},
                    'down_count':    {'title': 'Machine Stoppages',
                                      'x_axis': 'Datetime',
                                      'y_axis': 'Hourly Machine Stoppages'},
                    'down_secs':     {'title': 'Machine Downtime',
                                      'x_axis': 'Datetime',
                                      'y_axis': 'Hourly Downtime (secs)'},
                    'oee':           {'title': 'Operational Efficiency',
                                      'x_axis': 'Datetime',
                                      'y_axis': 'Operational Efficiency (%)'}
                    }
        rtn['chart_details'] = stat_map[stat]
        rtn['max_val'] = max_val  
         
        return rtn
    

class CurrentMachineStatus(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer,
                           db.ForeignKey('machines.id',
                                         ondelete='CASCADE'),
                           index=True)
    machine = db.relationship('Machines', backref=db.backref('status',
                                                             uselist=False))
    hourly_product_count = db.Column(db.Integer)
    is_down = db.Column(db.Boolean)
    last_down = db.Column(db.DateTime)
    hourly_down_count = db.Column(db.Integer)
    total_secs_down = db.Column(db.Integer)
    
    
class Machines(db.Model):
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20))
    
    def update_status(self):
        
        tick = current_app.config['UPDATE_CYCLE_SECS']
        
        if self.status.is_down:
            if ((dt.datetime.utcnow() - self.status.last_down).total_seconds() 
                > self.stats.min_downtime_secs):
                # Check to see if we come back up
                if random.random() < self.stats.restart_probability:
                    self.status.is_down = False
                else:
                    self.status.total_secs_down += tick
        else:
            # See if machine is going to go down
            if random.random() < self.stats.downtime_probability:
                self.status.is_down = True
                self.status.last_down = dt.datetime.utcnow()
                self.status.hourly_down_count += 1
            else:
                per_tick_prod_base = self.stats.ideal_run_rate * (tick / 60)
                per_tick_prod = self.stats.efficiency * per_tick_prod_base
                noise = random.uniform(0.9, 1.1)                    
                self.status.hourly_product_count += int(noise * per_tick_prod)
                
        db.session.commit()
    
    def reset_status(self):
        self.history.append(
            MachineHistory(datetime=dt.datetime.utcnow().replace(minute=0, 
                                                                 second=0, 
                                                                 microsecond=0),
                           product_count=self.status.hourly_product_count,
                           down_count=self.status.hourly_down_count,
                           down_secs=self.status.total_secs_down))
        
        db.session.commit()
        
        self.status.hourly_product_count = 0
        self.status.hourly_down_count = 0
        self.status.total_secs_down = 0
        db.session.commit()
        
    def get_average_hourly_production(self, lookback_weeks=4):
        MH = MachineHistory
        history = (db.session.query(func.avg(MH.product_count))
                     .filter(and_(MH.machine_id==self.id,
                                  MH.product_count > 0))
                     .first())
        if history is not None:
            return history[0]
        return history
    
    @staticmethod
    def get_current_status():
         
        rtn = []
         
        machines = Machines.query.order_by(Machines.name).all()
        for machine in machines:
            is_down = machine.status.is_down
            if is_down:
                total_secs_down = int((dt.datetime.utcnow() 
                                   - machine.status.last_down).total_seconds())
                mins_down = total_secs_down // 60
                secs_down = (total_secs_down - mins_down * 60) % 60
            else:
                mins_down = 0
                secs_down = 0
            
            machine_dict = {'machine_name': machine.name,
                            'is_down': is_down,
                            'secs_down': secs_down,
                            'mins_down': mins_down,
                            'prod_count': machine.status.hourly_product_count,
                            'down_count': machine.status.hourly_down_count}
            
            rtn.append(machine_dict)
        
        return rtn
              
    @staticmethod
    def _backdate_production(days=30):
        """Helper method to bootstrap production graphs with historical data

        In order for the production graphs to work and to enable schedule 
        optimisation, historical production data is required. This will generate
        hourly data for a period of time

        :param days: Number of days to generate historical data, defaults to 30
        """
        
        start = (dt.datetime.utcnow().replace(hour=0, minute=0, second=0, 
                                              microsecond=0)
                 - dt.timedelta(days=30))
        now = dt.datetime.utcnow()
        daterange = pd.date_range(start, now, freq='H').to_pydatetime()
        
        tick_length = current_app.config['UPDATE_CYCLE_SECS']
        
        machines = Machines.query.all()
        for machine in machines:
            stats = machine.stats
            machine_id = machine.id
            
            # Get the baseline production at stated efficiency
            hourly_production = np.full(len(daterange), 
                                        (stats.ideal_run_rate 
                                        * 60 * stats.efficiency))
            
            # Generate some noise of up to +/- 10% of production
            noise = np.random.uniform(0.9, 1.1, len(daterange))
            hourly_production *= noise
            
            # Run a few scenarios for downtimes for an hour
            scenarios = []
            ticks_per_hour = int(3600 / tick_length)
            min_downtime_ticks = stats.min_downtime_secs / tick_length
            for x in range(10):
                is_down = False
                went_down_tick = None
                down_count = 0
                down_secs = 0
                for tick in range(ticks_per_hour):
                    if is_down:
                        ticks_down = tick - went_down_tick
                        if ticks_down > min_downtime_ticks:
                            roll = random.random()
                            if roll < stats.restart_probability:
                                is_down = False
                                down_secs += ticks_down * tick_length
                    else:
                        roll = random.random()
                        if roll < stats.downtime_probability:
                            is_down = True
                            down_count += 1
                            went_down_tick = tick
                
                scenarios.append({'down_count': down_count,
                                  'down_secs': down_secs,
                                  'production_scaler': 1 - (down_secs / 3600)})
            
            # Pick from the scenarios randomly for each hour
            scenario_choices = np.random.choice(len(scenarios),
                                                len(daterange),
                                                replace=True)
            down_counts = [scenarios[x]['down_count'] 
                           for x in scenario_choices]
            down_secs = [scenarios[x]['down_secs'] 
                         for x in scenario_choices]
                
            # Scale hourly productivity to account for downtime
            scaling = np.array([scenarios[x]['production_scaler'] 
                                for x in scenario_choices])
            
            hourly_production *= scaling
            hourly_production = hourly_production.astype(int).tolist()
            
            # Expand out the machine id to match the number of entries
            machine_id = [machine_id for x in daterange]
            
            to_insert = list(zip(machine_id, daterange, hourly_production, 
                                 down_counts, down_secs))
            
            # Hacky way to get executemany
            with sqlite3.connect(current_app.config['DB_PATH']) as conn:
                c = conn.cursor()
                c.executemany("""
                              INSERT OR REPLACE INTO machine_history (
                                                           machine_id,
                                                           datetime,
                                                           product_count,
                                                           down_count,
                                                           down_secs)
                              VALUES (?, ?, ?, ?, ?)
                              """, to_insert)
                conn.commit()
    
    @staticmethod
    def _set_status():
        machines = Machines.query.all()
        
        # Take the last history reading, scale for the current minute and
        # set as current status
        scaler = dt.datetime.utcnow().minute / 60
        
        for machine in machines:
            history = (MachineHistory.query
                                     .filter_by(machine_id=machine.id)
                                     .order_by(MachineHistory.datetime.desc())
                                     .first())
            
            status = CurrentMachineStatus(
                        machine_id=machine.id,
                        is_down=False,
                        last_down=dt.datetime.utcnow(),
                        total_secs_down=int(history.down_secs * scaler),
                        hourly_down_count=int(history.down_count * scaler),
                        hourly_product_count=int(history.product_count * scaler)
                        )
            db.session.add(status)
        db.session.commit()
        
    @staticmethod
    def _bootstrap():
        machines = Machines.query.all()
        if machines:
            return
        
        for x in range(1, 5):
            new_machine = Machines(name=f'Machine {x}')
            db.session.add(new_machine)
            db.session.flush()
            machine_stats = current_app.config['MACHINE_STATS'][x]
            stat_entry = MachineStats(
                      machine_id=new_machine.id,
                      ideal_run_rate=machine_stats['ideal_run_rate'],
                      efficiency=machine_stats['efficiency'],
                      min_downtime_secs=machine_stats['min_downtime_secs'],
                      downtime_probability=machine_stats['downtime_probability'],
                      restart_probability=machine_stats['restart_probability']
                    )
            db.session.add(stat_entry)
        db.session.commit()
        
        # Clear any existing production data and bootstrap that too
        history = db.session.query(MachineHistory).delete()
        db.session.commit()
        Machines._backdate_production()
        db.session.commit()
        Machines._set_status()
    
    @staticmethod
    def get_all():
        return Machines.query.order_by('name').all()

              
class Problem:
    
    def __init__(self, request):
        self.req = request
        
        self.machine_products = {} # Product capabilities of each machine
        self.machines = Machines.get_all()
        self.machine_productivity = {}
        self.machine_shifts = {}
        
        self.forecast = {}
        self.daterange = None
        
        self.productivity_map = {}

        self.products = [int(item.split()[1]) 
                         for item in current_app.config['PRODUCT_NAMES']]
        self.product_name_map = dict(zip(self.products,
                                         current_app.config['PRODUCT_NAMES'])
                                     )
        
    def parse_request(self):
        
        valid_product_ids = set(self.products)
        valid_shift_names = set(current_app.config['SHIFT_HOURS'].keys())
        
        # First pull out the product list
        for i, machine in enumerate(current_app.config['MACHINE_NAMES']):
            product_list = self.req.getlist(f'machine_{i}_products[]')
            try:
                # The options should only come from a pre-defined dropdown.
                # Either the list is empty or it should be possible to split and
                # grab an int. Anything else is not to be trusted
                product_list = [int(item.split()[1]) for item in product_list]
                if any(item not in valid_product_ids for item in product_list):
                    return False, "Unable to recognise product ID"
                self.machine_products[self.machines[i].id] = product_list
                self.machine_productivity[self.machines[i].id] = (
                                self.machines[i].get_average_hourly_production()
                                )
            except Exception:
                return False, "Invalid product name"
            
        # Grab the shift pattern hours
        for i, machine in enumerate(current_app.config['MACHINE_NAMES']):
            shift_name = self.req.get(f'shift_pattern_{machine}')
            if shift_name and shift_name in valid_shift_names:
                self.machine_shifts[self.machines[i].id] = (
                                   current_app.config['SHIFT_HOURS'][shift_name]
                                   )
                
        # grab forecast
        try:
            forecast = pd.read_html(self.req.get('finalised_forecast_table'))[0]
        except Exception:
            # The forecast is added to the form on submission so always present
            return False, "Unknown error reading forecast"
        
        try:
            weeks = forecast.columns[1:]
            forecast[weeks] = forecast[weeks].astype(int)
            if len(forecast) != len(current_app.config['PRODUCT_NAMES']):
                return False, "Forecast length does not match product list"
        except ValueError:
            return False, "Forecast entries must be numeric"
        
        # Add in an additional "week" so that interpolation starts at 0
        forecast.insert(1, 'Week 0', 0)
        
        # Add in a final "week" so that we have something to interp up to
        forecast['Week 5'] = 0
        
        # Grab start date for the next Monday
        today = dt.date.today()
        days_to_add = 7 - today.weekday()
        next_monday = today + dt.timedelta(days=days_to_add)
        date_range = pd.date_range(start=next_monday, periods=6, freq='W-MON')
        
        # Transpose the df and get it at hourly granulatity using interpolate
        forecast = (forecast.set_index('Product Name')
                            .T
                            .set_index(pd.DatetimeIndex(date_range))
                            .cumsum())
        forecast = forecast.resample(rule='H').interpolate()
        
        self.daterange = forecast.index.astype(str).tolist()[:-1]
        
        for product_name in forecast.columns:
            product_id = int(product_name.split()[1])
            self.forecast[product_id] = forecast[product_name].values
        
        return True, 'success'
    
    def _build_productivity_array(self, ave_production, shift_overlay, 
                                  num_weeks):
        
        production = np.full(num_weeks * 168, ave_production)
        expanded_overlay = []
        week_pattern = []
        for day in range(7):
            week_pattern.extend(shift_overlay[day])
        
        full_pattern = []
        for x in range(num_weeks):
            full_pattern.extend(week_pattern)
        
        production *= full_pattern
        return production
    
    def _build_productivity_map(self):
        
        for machine in self.machines:
            shift_overlay = self.machine_shifts.get(machine.id)
            if not shift_overlay:
                # Machine has not had shifts configured. Turn it off.
                shift_overlay = current_app.config['SHIFT_HOURS']['null']
            
            expanded = self._build_productivity_array(
                                        self.machine_productivity[machine.id],
                                        shift_overlay,
                                        5)
            # Add the productivity but scale down by 1000 to match the units 
            # that the forecast is specified in
            self.productivity_map[machine.id] = expanded / 1000
            df = pd.DataFrame(self.productivity_map)
            
    def finalise_build(self):
        self._build_productivity_map()
        
    @staticmethod
    def create_forecast():
        forecast = []
        for product in current_app.config['PRODUCT_NAMES']:
            forecast.append([
                    product,
                    random.randint(50, 200) if random.random() > 0.4 else 0,
                    random.randint(50, 200) if random.random() > 0.4 else 0,
                    random.randint(50, 200) if random.random() > 0.4 else 0,
                    random.randint(50, 200) if random.random() > 0.4 else 0
                    ])
        
        return forecast
    

class Solver:
    
    def __init__(self, problem):
        self.problem = problem
        
        # ======================================================================
        # Defaults
        # ======================================================================
        self.min_swap_hours = 8    
        
        # Hours lost due to product switchover
        self.knockout_hours = {product_id: 1 for product_id
                               in self.problem.products}
        
        # Add a null product to all machine capabilities
        self.machine_products = {product_id: products + [0] 
                                 for product_id, products in 
                                 self.problem.machine_products.items()}
        self.machine_ids = [item.id for item in self.problem.machines]
        self.product_ids = self.problem.products
        
        # How far ahead to look before penalising over-production (hours)
        self.lookahead_hours_penalty_dict = {product_id: 24 for product_id 
                                             in self.problem.products}
        self.buffer_stock_percentage = 1.1
        
        # Simulated annealing params
        self.iterations = 10000
        self.temperature = 1
        self.alpha = 0.999
        self.max_idle = 1000
        
        self.default_knockout = 1
        
        # Swaps
        self.machine_swaps = np.random.choice(self.machine_ids, 
                                              self.iterations,
                                              replace=True).tolist()
        self.row_swaps = [0 for x in range(self.iterations)]
        self.product_swaps = [0 for x in range(self.iterations)]
        
        # Container to store individual product cost contributions to solution
        self.wip_cost_contributions = np.full(len(self.problem.products) + 1, 
                                              0).astype(np.float64)
        
        self.swap_indices = {}
        self.solution_max_index = (len(self.problem.daterange) - 
                                   (self.min_swap_hours + 1))
        self.solution = {machine.id: np.full(len(self.problem.daterange), 0)
                         for machine in self.problem.machines}          

        self.best_ever_cost = np.inf
        self.best_ever_production = {}
        self.best_ever_solution = {}
        
        # To store what a machine could be making at any time
        self.productivity_map = deepcopy(self.problem.productivity_map)
        
        # To store the WIP production per hour
        self.wip_production = {product_id: np.full(len(self.problem.daterange), 
                                                   0)
                               for product_id in self.problem.products}
        self.wip_demands = {product_id: self.problem.forecast[product_id][1:]
                            for product_id in self.problem.products}
        
        self.convergence = []
        
             
    def _get_swap_indices(self):
        """ Return list of swappable indices for each machine 
        
        Given that machines only run for certain periods of the day AND the fact 
        that there is a minimum amount of time that a machine can run one 
        product before it can switch again, it's possible to target the indices
        that are eligible to swap vs. just picking starting indices at random.
        
        Swapping at random gives a high chance of swapping in total downtime 
        (useless) in addition to giving product swaps at weird intervals e.g.
        one hour into a shift. This method is not without its flaws - it relies
        on shifts being generally regular in rotation. This is generally true.
        """
        
        for machine_id, productivity in self.problem.productivity_map.items():
            arr = productivity.nonzero()[0].tolist()

            swaps = []
            
            for k, g in groupby(enumerate(arr), lambda x: x[0]-x[1]):
                swaps.append(list(map(itemgetter(1), g)))
                chunked_swaps = [chunk(item, self.min_swap_hours) 
                                 for item in swaps]
                start_indices = [int(i[0]) for sublist in chunked_swaps 
                                 for i in sublist]
                
                # Drop the last index in case a swap here would go over the 
                # end of the array. We just have to live with this last item
                # being made
                self.swap_indices[machine_id] = start_indices[:-1]
    
    def _build_initial_solution(self):
        
        for machine in self.problem.machines:
            swap_indices = self.swap_indices.get(machine.id)
            if not swap_indices:
                continue
            for index in swap_indices:
                product = random.choice(self.machine_products[machine.id])
                self.solution[machine.id][index:index+self.min_swap_hours] = (
                                                                        product
                                                                        )
    
    def _get_initial_productivity(self):
        
        solution_matrix = pd.DataFrame(self.solution).values
        production_matrix = pd.DataFrame(self.productivity_map).values
        
        for product_id in self.problem.products:
            knockout_hours = self.knockout_hours.get(product_id, 0)
            
            if knockout_hours:
                local_solution = deepcopy(solution_matrix)
                local_productivity = deepcopy(production_matrix)
                
                rolled = np.roll(local_solution, knockout_hours, axis=0)
                indices = np.where(local_solution != rolled) 
                                
                local_productivity[indices[0], indices[1]] = 0
                
                production = np.where(local_solution == product_id, 
                                      local_productivity, 0).astype(np.float64)
            
            production = production.cumsum(axis=1)
            production = production[:, -1].cumsum()
            
            self.wip_production[product_id] = production.copy()
    
    def _generate_profiles(self):
        
        for i, machine_id in enumerate(self.machine_swaps):
            index_list = self.swap_indices.get(machine_id)
            if not index_list:
                continue
            product_list = self.machine_products[machine_id]
            
            self.row_swaps[i] = random.choice(index_list)
            self.product_swaps[i] = random.choice(product_list)
        
        self.acceptance_rolls = np.random.random(self.iterations)
        
    
    def _soft_solution_costs(self, wip, production):
        
        cost = 0

        demand = self.wip_demands[wip]
        missed_demand = (demand - production).clip(0).sum() * 5
        cost += missed_demand
        
        # OVERPRODUCTION
        lookahead_hours = self.lookahead_hours_penalty_dict.get(wip, 24)
        buffered_demand = demand * self.buffer_stock_percentage
        
        production_window = production[:-lookahead_hours]
        next_period_wip = buffered_demand[lookahead_hours:]
        
        if lookahead_hours > 0:
            over_prod = (production_window - next_period_wip).clip(0).sum()
            cost = cost + over_prod
        else:
            over_prod = (production - buffered_demand).clip(0).sum()
            cost = cost + over_prod
        
        final_window = production[-24:]
        final_demand = buffered_demand[-24:]
        over_prod = (final_window - final_demand).clip(0).sum()
        cost += over_prod
        
        return cost
    
    def _get_initial_solution_cost(self):
        for product_id in self.problem.products:
            production = self.wip_production[product_id]
            initial_cost = self._soft_solution_costs(product_id, 
                                                     production)
            self.wip_cost_contributions[product_id] = initial_cost
       
    def _add_remove_production(self, wip_modified):
        """
        Takes a list of dictionaries for wip codes that are added or removed
        from the production plan. Copies only the affected rows and returns
        the results of modification.
        
        Takes:
            {'new_wip_code': int, 'machine_index': int, 'start_row': int,
            'previous_wip_code': int, 'prior_product': int or None}
        """
        
        modified_wip_production = {}
        modified_solution = {}
        wip_cost_contributions = self.wip_cost_contributions.copy()
        
        for bundle in wip_modified:
            new_wip = bundle['new_wip_code']
            old_wip = bundle['previous_wip_code']
            machine = bundle['machine_index']
            row = bundle['start_row']
            prior_product = bundle['prior_product']
            next_product = bundle['next_product']
            
            _stop = row + self.min_swap_hours
            machine_production = self.productivity_map[machine][row:_stop]
            
            if new_wip == old_wip:
                # Can't alter solution cost, short-circuit
                continue
            
            if old_wip != 0:
                # Do we have to account for knockout on the wip we're removing?
                if old_wip != prior_product:
                    old_knockout = self.knockout_hours.get(old_wip, 
                                                           self.default_knockout
                                                           )
                else:
                    old_knockout = 0
                
                # Get the current production. Check first whether we've already
                # made some alteration on a previous iteration
                wip_production = modified_wip_production.get(
                                                    old_wip,
                                                    self.wip_production[old_wip]
                                                    ).copy()
                
                cumsum = machine_production[old_knockout:].cumsum()
                final_sum = machine_production[old_knockout:].sum()
                
                _start = row + old_knockout
                _stop = row + self.min_swap_hours
                wip_production[_start:_stop] -= cumsum
                wip_production[row + self.min_swap_hours:] -= final_sum
                
                # Store the modified values
                modified_wip_production[old_wip] = wip_production
                
            if new_wip != 0:
                # See whether this new product represents a product change
                if new_wip != prior_product:
                    new_knockout = self.knockout_hours.get(new_wip, 
                                                           self.default_knockout
                                                           )
                else:
                    new_knockout = 0
                
                # Get the current production. Check first whether we've already
                # made some alteration on a previous iteration
                wip_production = modified_wip_production.get(
                                                    new_wip,
                                                    self.wip_production[new_wip]
                                                    ).copy()
                
                cumsum = machine_production[new_knockout:].cumsum()
                final_sum = machine_production[new_knockout:].sum()
                
                _start = row+new_knockout
                _stop = row + self.min_swap_hours
                wip_production[_start:_stop] += cumsum
                
                wip_production[row + self.min_swap_hours:] += final_sum
                
                # Store the modified values
                modified_wip_production[new_wip] = wip_production
                machine_soln = modified_solution.get(machine,
                                                     self.solution[machine]
                                                     ).copy()
                
                machine_soln[row:row + self.min_swap_hours] = new_wip
                
                modified_solution[machine] = machine_soln
            
            if next_product and (next_product == new_wip): 
                    
                next_prod_knockout = self.knockout_hours.get(
                                            next_product, self.default_knockout
                                            )
                    
                if next_prod_knockout:
                    next_prod_production = (
                                modified_wip_production.get(next_product).copy()
                                )
                    
                    _start = row + self.min_swap_hours
                    _stop = row + self.min_swap_hours + next_prod_knockout
                    machine_productivity = (
                                    self.productivity_map[machine][_start:_stop]
                                    )
                    
                    _start = row + self.min_swap_hours
                    _stop = row + self.min_swap_hours+next_prod_knockout
                    _increment = machine_productivity.cumsum()
                    next_prod_production[_start:_stop] += _increment
                    next_prod_production[_stop:] += machine_productivity.sum()
                    
                    modified_wip_production[next_product] = next_prod_production    
            
            if next_product and (next_product == old_wip):
                    
                next_prod_knockout = self.knockout_hours.get(
                                            next_product, self.default_knockout
                                            )
                    
                if next_prod_knockout:
                    next_prod_production = modified_wip_production.get(
                                next_product, self.wip_production[next_product]
                                ).copy()
                    
                    _start = row + self.min_swap_hours
                    _stop = row + self.min_swap_hours + next_prod_knockout
                    machine_productivity = (
                                    self.productivity_map[machine][_start:_stop]
                                    )

                    _start = row + self.min_swap_hours
                    _stop = row + self.min_swap_hours+next_prod_knockout
                    _increment = machine_productivity.cumsum()
                    next_prod_production[_start:_stop] -= _increment
                    next_prod_production[_stop:] -= machine_productivity.sum()
                
                    modified_wip_production[next_product] = next_prod_production
            
            machine_soln = modified_solution.get(machine,
                                      self.solution[machine]).copy()
                
            machine_soln[row:row+self.min_swap_hours] = new_wip
                
            modified_solution[machine] = machine_soln
            
        # Now get the new costs
        for wip_code, production in modified_wip_production.items():
            wip_cost_contributions[wip_code] = (
                                self._soft_solution_costs(wip_code, production)
                                )
        
        return (modified_wip_production, 
                modified_solution, 
                wip_cost_contributions)
        
    def _run_solution_loop(self):
        
        # Grab the starting values
        self._get_initial_solution_cost()
        current_best_cost = self.wip_cost_contributions.sum()
        best_ever_cost = current_best_cost
        
        self.best_ever_production = deepcopy(self.wip_production)
        self.best_ever_solution = deepcopy(self.solution)
        
        for x in range(self.iterations):
            
            machine = self.machine_swaps[x]
            row = self.row_swaps[x]
            new_product = self.product_swaps[x]
            previous_product = self.solution[machine][row]
            
            if row > 0:
                prior_running = self.solution[machine][row - 1]
            else:
                prior_running = None
            
            # Prevent us indexing beyond the length of the solution
            if row < self.solution_max_index:
                next_product = (self.solution[machine][row+self.min_swap_hours+1])
            else:
                next_product = None
                
            bundle = [{'new_wip_code': new_product, 
                       'machine_index': machine, 
                       'start_row': row,
                       'previous_wip_code': previous_product,
                       'prior_product': prior_running,
                       'next_product': next_product}]
        
            mod_prod, mod_soln, costs = self._add_remove_production(bundle)
            new_cost = costs.sum()
            
            if new_cost < current_best_cost:
                current_best_cost = new_cost
                
                self.wip_cost_contributions = costs.copy()
                self.convergence.append([x, new_cost])
                
                for k, v in mod_prod.items():
                    self.wip_production[k] = v.copy()
                
                for k, v in mod_soln.items():
                    self.solution[k] = v.copy()
                    
                if new_cost < best_ever_cost:
                    best_ever_cost = new_cost
                    self.best_ever_production = deepcopy(self.wip_production)
                    self.best_ever_solution = deepcopy(self.solution)
            
            else:
                acceptance = exp(
                    ((current_best_cost - new_cost) / current_best_cost ) * 100
                      / self.temperature + 0.00001)
                
                if acceptance > self.acceptance_rolls[x]:
                    current_best_cost = new_cost
                    
                    self.wip_cost_contributions = costs.copy()
                    self.convergence.append([x, new_cost])
                    
                    for k, v in mod_prod.items():
                        self.wip_production[k] = v.copy()
                    
                    for k, v in mod_soln.items():
                        self.solution[k] = v.copy()
                
            self.temperature *= self.alpha
    
    def run_solver(self):
        self._get_swap_indices()
        self._build_initial_solution()
        self._get_initial_productivity()
        self._generate_profiles()
        self._run_solution_loop()   
    
    
class Results:
    
    def __init__(self, solved_problem):
        
        self.solver = solved_problem
        self.daterange = self.solver.problem.daterange
        self.product_name_map = self.solver.problem.product_name_map
        self.product_name_map[0] = 'Offline'
        self.convergence = self.solver.convergence
        self.wip_demands = self.solver.wip_demands
        self.best_ever_production = self.solver.best_ever_production
        self.best_ever_solution = self.solver.best_ever_solution
        self.productivity_map = self.solver.productivity_map
        
        self.machine_name_map = dict(zip(self.solver.machine_ids,
                                     current_app.config['MACHINE_NAMES'])
                                    )
       
    def _get_shift_rotation(self):
        
        soln_df = pd.DataFrame(self.best_ever_solution)
        soln_df = soln_df.rename(columns=self.machine_name_map)
        soln_df = soln_df.applymap(self.product_name_map.get)
        soln_df.insert(0, 'Shift Start', self.daterange)
        soln_df = soln_df.iloc[6:].iloc[::8, :]
        
        soln_df['Shift Start'] = (pd.to_datetime(soln_df['Shift Start'])
                                    .dt.strftime('%H:%M %a %d/%m/%y'))
        headers = soln_df.columns.values.tolist()
        return soln_df.values.tolist(), headers
    
    def _get_machine_utilisation(self):
        
        wc_dates = (np.array(self.daterange).reshape((-1, 168))[:, :1]
                                            .ravel()
                                            .tolist())
        
        utilisation = []
        
        for machine_id, possible_production in self.productivity_map.items():
            actual_production = self.best_ever_solution[machine_id]
            can_produce = (np.where(possible_production > 0, 1, 0)
                             .reshape((-1, 168))
                             .sum(axis=1)
                             .astype(float))
            did_produce = (np.where(actual_production > 0, 1, 0)
                             .reshape((-1, 168))
                             .sum(axis=1)
                             .astype(float))
            
            weekly_utilisation = np.divide(did_produce, 
                                           can_produce, 
                                           out=np.zeros_like(can_produce), 
                                           where=can_produce!=0)
            weekly_utilisation = (weekly_utilisation * 100).tolist()
            
            utilisation.append({'machine_name': self.machine_name_map[machine_id],
                                'utilisation': weekly_utilisation})
            
        return utilisation, wc_dates
     
    def get_solution(self):
        
        rtn = {}
        results = []
        
        shift_table, table_headers = self._get_shift_rotation()
        utilisation, wc_dates = self._get_machine_utilisation()
        
        for product_id, production in self.best_ever_production.items():
            results.append({
                    'product_name': self.product_name_map[product_id],
                    'demand': self.wip_demands[product_id].astype(int).tolist(),
                    'production': production.astype(int).tolist()
                    })
        rtn['productivity_graphs'] = results
        rtn['datetimes'] = self.daterange
        rtn['convergence'] = {'x': [item[0] for item in self.convergence][::20],
                              'cost': [int(item[1]) for item in self.convergence][::20]
                              }
        print("x", len(rtn['convergence']['x']))
        print("cost", len(rtn['convergence']['cost']))
        rtn['shift_table'] = shift_table
        rtn['shift_table_headers'] = table_headers
        rtn['utilisation'] = utilisation
        rtn['wc_dates'] = wc_dates
        
        return rtn