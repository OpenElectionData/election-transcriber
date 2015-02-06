from flask import Blueprint, make_response, request
import json

views = Blueprint('views', __name__)

@views.route('/')
def index():
    return make_response(json.dumps({}))
