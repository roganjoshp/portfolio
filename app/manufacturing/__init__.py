from flask import Blueprint

bp = Blueprint('manufacturing', __name__)

from app.manufacturing import routes