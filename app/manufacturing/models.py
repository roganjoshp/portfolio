import random
import sqlite3

from flask import current_app

from app import db

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