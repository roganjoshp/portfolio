import csv
import os
import platform
import string

from dotenv import load_dotenv
from flask import current_app


basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    DB_PATH = 'app/app.db'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, DB_PATH)
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_TYPE = 'sqlalchemy'
    SESSION_SQLALCHEMY_TABLE = 'sessions'
    
    RECAPTCHA_PUBLIC_KEY = os.environ.get('RECAPTCHA_PUBLIC_KEY')
    RECAPTCHA_PRIVATE_KEY = os.environ.get('RECAPTCHA_PRIVATE_KEY')
    RECAPTCHA_PARAMETERS = {'hl': 'zh', 'render': 'explicit'}
    RECAPTCHA_DATA_ATTRS = {'theme': 'light'}
    
    PERMANENT_SESSION_LIFETIME = 604800
    WTF_CSRF_TIME_LIMIT = None
    
    SCHEDULER_API_ENABLED = True
    
    # VEHICLE ROUTING PARAMS
    
    MIN_LAT = 53.384
    MAX_LAT = 53.573
    MIN_LON = -2.398
    MAX_LON = -2.065

    WH_LAT = 53.470795
    WH_LON = -2.327794

    NUM_CUSTOMERS = list(range(10, 110, 10))
    NUM_DRIVERS = list(range(1, 6))
    TIME_SLOTS = list(range(1, 6))
    DRIVER_BREAKS = ['Yes', 'No']
    
    START_TIMES = [540, 600, 660, 720, 780, 840, 900] # Mins past midnight

    OSRM_BASE = os.environ.get('OSRM_BASE')
    OSRM_END = '?annotations=distance,duration'
    
    LEAFLET_SERVER = os.environ.get('LEAFLET_ROUTING_SERVER')
    MAPBOX_KEY = os.environ.get('MAPBOX_KEY')
    JSPRIT_SOCKET = os.environ.get('JSPRIT_SOCKET')
    REQUEST_PATH = os.path.join(basedir, 'app/requests')
    
    @staticmethod
    def load_customer_names():
        """ Pre-load the static customer names for the routing problems """
        
        path = os.path.join(basedir, 'app/static/files/random_names.csv')
        with open(path) as infile:
            reader = csv.reader(infile)
            names = list(set([' '.join(sublist) for sublist in reader]))
        return names
    
    # PRODUCTION SCHEDULING PARAMS
    
    SCHEDULER_API_ENABLED = True
    
    MACHINE_STATS = {
         1: {'ideal_run_rate': 100,
             'efficiency': 0.85,
             'min_downtime_secs': 20,
             'downtime_probability': 0.04,
             'restart_probability': 0.3},
         2: {'ideal_run_rate': 100,
             'efficiency': 0.9,
             'min_downtime_secs': 120,
             'downtime_probability': 0.02,
             'restart_probability': 0.3},
         3: {'ideal_run_rate': 100,
             'efficiency': 0.75,
             'min_downtime_secs': 50,
             'downtime_probability': 0.01,
             'restart_probability': 0.3},
         4: {'ideal_run_rate': 100,
             'efficiency': 0.6,
             'min_downtime_secs': 10,
             'downtime_probability': 0.06,
             'restart_probability': 0.3}
         }
        
    # How often to generate new machine data and update in real-time on frontend
    UPDATE_CYCLE_SECS = 3
    
    SHIFT_PATTERNS = ['6-2', '2-10', '6-2 and 2-10']
    
    # Hard-code the general shift pattern hours. Normally these could be 
    # customised on the front-end to include even fractions of hours, but this
    # is overkill
    SHIFT_HOURS = {
        'null':        {0: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        1: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        2: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        3: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        4: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        5: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        6: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},
        '6-2':         {0: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0],
                        1: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0],
                        2: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0],
                        3: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0],
                        4: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0],
                        5: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        6: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},
        '2-10':        {0: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0],
                        1: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0],
                        2: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0],
                        3: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0],
                        4: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,0,0],
                        5: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        6: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},
        '6-2 and 2-10':{0: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
                        1: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
                        2: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
                        3: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
                        4: [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,0],
                        5: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                        6: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]}
        }
    
    MACHINE_NAMES = [f'Machine {x}' for x in string.ascii_uppercase[:4]]
    PRODUCT_NAMES = [f'Product {x}' for x in range(1, 9)]
    