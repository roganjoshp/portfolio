import os

from flask import Flask

from flask_apscheduler import APScheduler
from flask_migrate import Migrate
from flask_session import Session, SqlAlchemySessionInterface
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from sqlalchemy import MetaData
from sqlalchemy.exc import OperationalError

from config import Config


meta = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s"
      })

csrf = CSRFProtect()
db = SQLAlchemy(metadata=meta)
migrate = Migrate()
scheduler = APScheduler()
sess = Session()


def create_app(config_class=Config):
    
    app = Flask(__name__)

    app.config.from_object(config_class)
    db.init_app(app)
    db.metadata.clear()
    
    csrf.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    
    sess.init_app(app)
    SqlAlchemySessionInterface(app, db, "sessions", "sess_")
    scheduler.init_app(app)
    
    app.config['CUSTOMER_NAMES'] = config_class.load_customer_names()
    app.jinja_env.globals.update(mapbox_key=app.config['MAPBOX_KEY'])
    app.jinja_env.globals.update(leaflet_router=app.config['LEAFLET_SERVER'])
    app.jinja_env.globals.update(sitekey=app.config['RECAPTCHA_PUBLIC_KEY'])
    
    # Register blueprints
    from app.core import bp as core
    app.register_blueprint(core)
    
    from app.vehicle_routing import bp as routing
    app.register_blueprint(routing, url_prefix='/routing')
    
    from app.manufacturing import bp as manufacturing
    app.register_blueprint(manufacturing, url_prefix='/manufacturing')
    
    try:
        # Bootstrap the machine data
        from app.manufacturing.models import Machines
        with app.app_context():
            Machines._bootstrap()
            
        # Only when schema in place and machines have been bootstrapped, start
        # Also turn off when in debug mode
        #if not os.environ.get('FLASK_DEBUG', False):       
        scheduler.start()
        
    except OperationalError:
        print('There are unapplied database migrations')
    
    return app