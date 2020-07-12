from flask import Blueprint

bp = Blueprint('routing', __name__)

from app.vehicle_routing import routes