from flask import Flask

from flask_migrate import Migrate
from flask_session import Session, SqlAlchemySessionInterface
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from sqlalchemy import MetaData

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
    
    app.config['CUSTOMER_NAMES'] = config_class.load_customer_names()
    app.jinja_env.globals.update(mapbox_key=app.config['MAPBOX_KEY'])
    app.jinja_env.globals.update(leaflet_router=app.config['LEAFLET_SERVER'])
    
    # Register blueprints
    from app.core import bp as core
    app.register_blueprint(core)
    
    from app.vehicle_routing import bp as routing
    app.register_blueprint(routing, url_prefix='/routing')
    
    return app